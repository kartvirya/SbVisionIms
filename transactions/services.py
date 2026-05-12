from decimal import Decimal

from django.db import transaction as db_transaction
from django.db.models import Sum, Case, When, DecimalField

from accounts.models import Customer, Vendor
from store.models import Item
from transactions.models import (
    CustomerPayment,
    InventoryTransaction,
    InventoryTransactionItem,
    LedgerEntry,
    Purchase,
    StockMovement,
    VendorPayment,
)


def _to_decimal(value):
    return Decimal(str(value))


def get_available_stock(item: Item) -> Decimal:
    """
    Return current stock based on stock movements.
    Falls back to cached item.quantity if no movements exist yet.
    """
    if not item.stock_movements.exists():
        return _to_decimal(item.quantity)

    totals = item.stock_movements.aggregate(
        stock_in=Sum(
            Case(
                When(movement_type=StockMovement.MovementType.IN, then="quantity"),
                default=Decimal("0"),
                output_field=DecimalField(max_digits=12, decimal_places=3),
            )
        ),
        stock_out=Sum(
            Case(
                When(movement_type=StockMovement.MovementType.OUT, then="quantity"),
                default=Decimal("0"),
                output_field=DecimalField(max_digits=12, decimal_places=3),
            )
        ),
    )
    return (totals["stock_in"] or Decimal("0")) - (totals["stock_out"] or Decimal("0"))


def delete_inventory_transaction_and_sync(transaction_obj):
    """Remove a posted inventory transaction and refresh affected item quantity caches."""
    if not transaction_obj:
        return
    affected_items = [
        movement.item for movement in transaction_obj.stock_movements.select_related("item")
    ]
    transaction_obj.delete()
    if affected_items:
        sync_item_quantity_cache(affected_items)


def sync_item_quantity_cache(items):
    """
    Keep Item.quantity as a cache derived from movement ledger.
    """
    unique_items = {item.id: item for item in items}.values()
    for item in unique_items:
        item.quantity = int(get_available_stock(item))
        item.save(update_fields=["quantity"])


def _build_items(transaction_obj, items):
    created_items = []
    total_amount = Decimal("0")

    for row in items:
        item = row["item"]
        if isinstance(item, int):
            item = Item.objects.get(pk=item)

        quantity = _to_decimal(row["quantity"])
        unit_price = _to_decimal(row["unit_price"])
        line_total = quantity * unit_price

        created_item = InventoryTransactionItem.objects.create(
            transaction=transaction_obj,
            item=item,
            quantity=quantity,
            unit_price=unit_price,
            line_total=line_total,
        )
        created_items.append(created_item)
        total_amount += line_total

    transaction_obj.total_amount = total_amount
    transaction_obj.save(update_fields=["total_amount"])
    return created_items


def _create_stock_movements(transaction_obj, items, movement_type):
    StockMovement.objects.bulk_create(
        [
            StockMovement(
                item=line.item,
                transaction=transaction_obj,
                movement_type=movement_type,
                quantity=line.quantity,
            )
            for line in items
        ]
    )


def _create_ledger_entries(transaction_obj, entries):
    LedgerEntry.objects.bulk_create(
        [
            LedgerEntry(
                transaction=transaction_obj,
                account=entry["account"],
                debit=_to_decimal(entry.get("debit", 0)),
                credit=_to_decimal(entry.get("credit", 0)),
            )
            for entry in entries
        ]
    )


def _source_ref(source_ref=None, source_model=None, source_id=None):
    if source_ref:
        return source_ref
    if source_model and source_id:
        return f"{source_model}:{source_id}"
    return None


@db_transaction.atomic
def create_purchase_transaction(
    *,
    vendor: Vendor,
    items,
    notes="",
    total_amount=None,
    source_ref=None,
):
    """
    Create a purchase transaction with items, stock movements, and ledger rows.
    """
    source_reference = _source_ref(source_ref=source_ref)
    transaction_obj = None
    if source_reference:
        transaction_obj = InventoryTransaction.objects.filter(
            source_ref=source_reference,
            transaction_type=InventoryTransaction.TransactionType.PURCHASE,
        ).first()
    if transaction_obj:
        InventoryTransactionItem.objects.filter(transaction=transaction_obj).delete()
        StockMovement.objects.filter(transaction=transaction_obj).delete()
        LedgerEntry.objects.filter(transaction=transaction_obj).delete()
        transaction_obj.vendor = vendor
        transaction_obj.notes = notes
        transaction_obj.status = InventoryTransaction.TransactionStatus.POSTED
        transaction_obj.save(update_fields=["vendor", "notes", "status"])
    else:
        transaction_obj = InventoryTransaction.objects.create(
            transaction_type=InventoryTransaction.TransactionType.PURCHASE,
            status=InventoryTransaction.TransactionStatus.POSTED,
            vendor=vendor,
            notes=notes,
            source_ref=source_reference,
        )

    created_items = _build_items(transaction_obj, items)
    if total_amount is not None:
        transaction_obj.total_amount = _to_decimal(total_amount)
        transaction_obj.save(update_fields=["total_amount"])
    _create_stock_movements(transaction_obj, created_items, StockMovement.MovementType.IN)
    _create_ledger_entries(
        transaction_obj,
        [
            {"account": "Inventory", "debit": transaction_obj.total_amount, "credit": 0},
            {"account": "Accounts Payable", "debit": 0, "credit": transaction_obj.total_amount},
        ],
    )
    sync_item_quantity_cache([line.item for line in created_items])
    return transaction_obj


def get_weighted_average_unit_cost(item: Item) -> Decimal:
    """
    Unit cost from all posted purchase lines for this item (simple moving average).
    Falls back to Item.cost_price when there is no purchase history.
    """
    agg = InventoryTransactionItem.objects.filter(
        item=item,
        transaction__transaction_type=InventoryTransaction.TransactionType.PURCHASE,
    ).aggregate(tq=Sum("quantity"), tv=Sum("line_total"))
    tq, tv = agg["tq"], agg["tv"]
    if tq and tq > 0 and tv is not None:
        return _to_decimal(tv) / _to_decimal(tq)
    return _to_decimal(item.cost_price or 0)


@db_transaction.atomic
def create_sale_transaction(*, customer: Customer, items, notes=""):
    """
    Create a sale transaction with items, stock movements, and ledger rows.
    """
    transaction_obj = InventoryTransaction.objects.create(
        transaction_type=InventoryTransaction.TransactionType.SALE,
        status=InventoryTransaction.TransactionStatus.POSTED,
        customer=customer,
        notes=notes,
    )

    normalized_items = []
    for row in items:
        item = row["item"]
        if isinstance(item, int):
            item = Item.objects.get(pk=item)
        quantity = _to_decimal(row["quantity"])
        available_stock = get_available_stock(item)
        if quantity > available_stock:
            raise ValueError(f"Not enough stock for item: {item.name}")
        normalized_items.append(
            {
                "item": item,
                "quantity": quantity,
                "unit_price": _to_decimal(row["unit_price"]),
            }
        )

    created_items = _build_items(transaction_obj, normalized_items)
    _create_stock_movements(transaction_obj, created_items, StockMovement.MovementType.OUT)

    cogs_total = Decimal("0")
    for line in created_items:
        unit_cost = get_weighted_average_unit_cost(line.item)
        cogs_total += unit_cost * line.quantity

    ledger_rows = [
        {"account": "Accounts Receivable", "debit": transaction_obj.total_amount, "credit": 0},
        {"account": "Sales Revenue", "debit": 0, "credit": transaction_obj.total_amount},
    ]
    if cogs_total > 0:
        ledger_rows.extend(
            [
                {"account": "Cost of Goods Sold", "debit": cogs_total, "credit": 0},
                {"account": "Inventory", "debit": 0, "credit": cogs_total},
            ]
        )
    _create_ledger_entries(transaction_obj, ledger_rows)
    sync_item_quantity_cache([line.item for line in created_items])
    return transaction_obj


def purchase_stock_item_rows(purchase: Purchase):
    """Build line dicts for inventory posting from PurchaseLine or legacy header fields."""
    rows = []
    if purchase.lines.exists():
        for line in purchase.lines.select_related("item"):
            rows.append(
                {
                    "item": line.item_id,
                    "quantity": line.quantity,
                    "unit_price": line.unit_price,
                }
            )
    elif purchase.item_id:
        rows.append(
            {
                "item": purchase.item_id,
                "quantity": purchase.quantity,
                "unit_price": purchase.price,
            }
        )
    return rows


def clear_purchase_inventory_posting(purchase: Purchase):
    """Remove posted stock/ledger for this purchase if any."""
    if not purchase.pk:
        return
    txn = getattr(purchase, "inventory_transaction", None)
    if txn:
        delete_inventory_transaction_and_sync(txn)
    Purchase.objects.filter(pk=purchase.pk).update(inventory_transaction=None)


@db_transaction.atomic
def sync_purchase_inventory_transaction(*, purchase, notes_suffix=""):
    """
    Post or refresh purchase stock when receipt_status is Received; otherwise unpost.
    """
    if purchase.receipt_status != "S":
        clear_purchase_inventory_posting(purchase)
        return None

    rows = purchase_stock_item_rows(purchase)
    if not rows:
        clear_purchase_inventory_posting(purchase)
        return None

    notes = f"Purchase #{purchase.id}{notes_suffix}"
    transaction_obj = create_purchase_transaction(
        vendor=purchase.vendor,
        items=rows,
        notes=notes,
        total_amount=purchase.net_amount,
        source_ref=f"purchase:{purchase.id}",
    )
    if purchase.inventory_transaction_id != transaction_obj.id:
        purchase.inventory_transaction = transaction_obj
        purchase.save(update_fields=["inventory_transaction"])
    return transaction_obj


@db_transaction.atomic
def post_vendor_payment_ledger(*, payment: VendorPayment):
    """Dr AP, Cr Cash/Bank for a vendor payment (idempotent by source_ref)."""
    source_ref = f"vendor_payment:{payment.id}"
    existing = InventoryTransaction.objects.filter(
        source_ref=source_ref,
        transaction_type=InventoryTransaction.TransactionType.PAYMENT,
    ).first()
    if existing:
        return existing

    credit_account = "Cash" if payment.method == "cash" else "Bank"
    txn = InventoryTransaction.objects.create(
        transaction_type=InventoryTransaction.TransactionType.PAYMENT,
        status=InventoryTransaction.TransactionStatus.POSTED,
        vendor=payment.purchase.vendor,
        notes=f"Vendor payment #{payment.id} (Purchase #{payment.purchase_id})",
        source_ref=source_ref,
        total_amount=payment.amount,
    )
    _create_ledger_entries(
        txn,
        [
            {"account": "Accounts Payable", "debit": payment.amount, "credit": 0},
            {"account": credit_account, "debit": 0, "credit": payment.amount},
        ],
    )
    VendorPayment.objects.filter(pk=payment.pk).update(inventory_transaction=txn)
    return txn


@db_transaction.atomic
def post_customer_payment_ledger(*, payment: CustomerPayment):
    """Dr Cash/Bank, Cr AR for a customer receipt."""
    source_ref = f"customer_payment:{payment.id}"
    existing = InventoryTransaction.objects.filter(
        source_ref=source_ref,
        transaction_type=InventoryTransaction.TransactionType.PAYMENT,
    ).first()
    if existing:
        return existing

    debit_account = "Cash" if payment.method == "cash" else "Bank"
    txn = InventoryTransaction.objects.create(
        transaction_type=InventoryTransaction.TransactionType.PAYMENT,
        status=InventoryTransaction.TransactionStatus.POSTED,
        customer=payment.sale.customer,
        notes=f"Customer payment #{payment.id} (Sale #{payment.sale_id})",
        source_ref=source_ref,
        total_amount=payment.amount,
    )
    _create_ledger_entries(
        txn,
        [
            {"account": debit_account, "debit": payment.amount, "credit": 0},
            {"account": "Accounts Receivable", "debit": 0, "credit": payment.amount},
        ],
    )
    CustomerPayment.objects.filter(pk=payment.pk).update(inventory_transaction=txn)
    return txn


def delete_payment_ledger(payment):
    """Remove ledger transaction linked to a payment record if present."""
    txn_id = getattr(payment, "inventory_transaction_id", None)
    if not txn_id:
        return
    InventoryTransaction.objects.filter(pk=txn_id).delete()
    type(payment).objects.filter(pk=payment.pk).update(inventory_transaction=None)


def get_stock_ledger_rows(*, item=None, date_from=None, date_to=None):
    queryset = StockMovement.objects.select_related("item", "transaction").order_by("created_at", "id")
    if item:
        queryset = queryset.filter(item=item)
    if date_from:
        queryset = queryset.filter(created_at__date__gte=date_from)
    if date_to:
        queryset = queryset.filter(created_at__date__lte=date_to)

    running_totals = {}
    rows = []
    for move in queryset:
        key = move.item_id
        if key not in running_totals:
            opening = move.item.stock_movements.filter(
                created_at__lt=move.created_at,
            ).aggregate(
                stock_in=Sum(
                    Case(
                        When(movement_type=StockMovement.MovementType.IN, then="quantity"),
                        default=Decimal("0"),
                        output_field=DecimalField(max_digits=12, decimal_places=3),
                    )
                ),
                stock_out=Sum(
                    Case(
                        When(movement_type=StockMovement.MovementType.OUT, then="quantity"),
                        default=Decimal("0"),
                        output_field=DecimalField(max_digits=12, decimal_places=3),
                    )
                ),
            )
            running_totals[key] = (opening["stock_in"] or Decimal("0")) - (
                opening["stock_out"] or Decimal("0")
            )

        direction = Decimal("1") if move.movement_type == StockMovement.MovementType.IN else Decimal("-1")
        running_totals[key] = running_totals[key] + (direction * move.quantity)
        rows.append(
            {
                "created_at": move.created_at,
                "item": move.item,
                "movement_type": move.movement_type,
                "quantity": move.quantity,
                "source_ref": move.transaction.source_ref or f"txn:{move.transaction_id}",
                "running_qty": running_totals[key],
            }
        )
    return rows


def get_payables_aging():
    return (
        Vendor.objects.filter(purchases__amount_remaining__gt=0)
        .annotate(total_outstanding=Sum("purchases__amount_remaining"))
        .order_by("-total_outstanding")
    )
