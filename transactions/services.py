from decimal import Decimal

from django.db import transaction as db_transaction
from django.utils import timezone
from django.db.models import (
    Sum,
    Max,
    Case,
    When,
    DecimalField,
    F,
    OuterRef,
    Subquery,
    ExpressionWrapper,
    Value,
)
from django.db.models.functions import Coalesce

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


@db_transaction.atomic
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
    """Keep Item.quantity cache aligned with ledger + variant stock."""
    from store.stock_utils import get_item_current_stock

    unique_items = {item.id: item for item in items}.values()
    for item in unique_items:
        item.quantity = get_item_current_stock(item)
        item.save(update_fields=["quantity"])


@db_transaction.atomic
def reconcile_ledger_stock_to_target(item, target_ledger_qty, notes="Stock adjustment"):
    """
    Post an inventory adjustment so ledger on-hand matches target_ledger_qty.
    Variant quantities are managed separately and added to displayed totals.
    """
    from store.stock_utils import get_ledger_stock

    source_ref = f"adjustment:item:{item.id}"
    existing = InventoryTransaction.objects.filter(
        source_ref=source_ref,
        transaction_type=InventoryTransaction.TransactionType.ADJUSTMENT,
    ).first()
    if existing:
        StockMovement.objects.filter(transaction=existing).delete()
        InventoryTransactionItem.objects.filter(transaction=existing).delete()
        existing.delete()

    target = int(_to_decimal(target_ledger_qty))
    current = int(get_ledger_stock(item))
    delta = target - current
    if delta == 0:
        sync_item_quantity_cache([item])
        return None

    movement_type = (
        StockMovement.MovementType.IN if delta > 0 else StockMovement.MovementType.OUT
    )
    txn = InventoryTransaction.objects.create(
        transaction_type=InventoryTransaction.TransactionType.ADJUSTMENT,
        status=InventoryTransaction.TransactionStatus.POSTED,
        notes=notes,
        source_ref=source_ref,
    )
    qty = abs(delta)
    line = InventoryTransactionItem.objects.create(
        transaction=txn,
        item=item,
        quantity=qty,
        unit_price=Decimal("0"),
        line_total=Decimal("0"),
    )
    StockMovement.objects.create(
        item=item,
        transaction=txn,
        movement_type=movement_type,
        quantity=qty,
    )
    txn.total_amount = Decimal("0")
    txn.save(update_fields=["total_amount"])
    sync_item_quantity_cache([item])
    return txn


def deduct_variant_stock(variation_id, quantity):
    """Reduce variant quantity after a sale."""
    from store.models import ProductVariation

    variation = ProductVariation.objects.select_for_update().get(pk=variation_id)
    new_qty = int(variation.quantity or 0) - int(quantity)
    if new_qty < 0:
        raise ValueError(f"Not enough stock for variant: {variation}")
    variation.quantity = new_qty
    variation.save(update_fields=["quantity"])
    sync_item_quantity_cache([variation.item])


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

    from store.stock_utils import get_sellable_stock

    normalized_items = []
    for row in items:
        item = row["item"]
        if isinstance(item, int):
            item = Item.objects.get(pk=item)
        quantity = _to_decimal(row["quantity"])
        variation_id = row.get("variation_id")
        available = get_sellable_stock(item, variation_id=variation_id)
        if quantity > available:
            label = item.name
            if variation_id:
                label += " (selected variant)"
            raise ValueError(f"Not enough stock for: {label}")
        if variation_id:
            deduct_variant_stock(variation_id, int(quantity))
        normalized_items.append(
            {
                "item": item,
                "quantity": quantity,
                "unit_price": _to_decimal(row["unit_price"]),
                "variation_id": variation_id,
            }
        )

    created_items = _build_items(transaction_obj, normalized_items)
    ledger_lines = [
        line
        for line, row in zip(created_items, normalized_items)
        if not row.get("variation_id")
    ]
    if ledger_lines:
        _create_stock_movements(
            transaction_obj, ledger_lines, StockMovement.MovementType.OUT
        )
    sync_item_quantity_cache([row["item"] for row in normalized_items])

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
    credit_account = "Cash" if payment.method == "cash" else "Bank"
    ledger_rows = [
        {"account": "Accounts Payable", "debit": payment.amount, "credit": 0},
        {"account": credit_account, "debit": 0, "credit": payment.amount},
    ]
    if existing:
        existing.total_amount = payment.amount
        existing.vendor = payment.purchase.vendor
        existing.notes = (
            f"Vendor payment #{payment.id} (Purchase #{payment.purchase_id})"
        )
        existing.save(update_fields=["total_amount", "vendor", "notes"])
        LedgerEntry.objects.filter(transaction=existing).delete()
        _create_ledger_entries(existing, ledger_rows)
        return existing

    txn = InventoryTransaction.objects.create(
        transaction_type=InventoryTransaction.TransactionType.PAYMENT,
        status=InventoryTransaction.TransactionStatus.POSTED,
        vendor=payment.purchase.vendor,
        notes=f"Vendor payment #{payment.id} (Purchase #{payment.purchase_id})",
        source_ref=source_ref,
        total_amount=payment.amount,
    )
    _create_ledger_entries(txn, ledger_rows)
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
    debit_account = "Cash" if payment.method == "cash" else "Bank"
    ledger_rows = [
        {"account": debit_account, "debit": payment.amount, "credit": 0},
        {"account": "Accounts Receivable", "debit": 0, "credit": payment.amount},
    ]
    if existing:
        existing.total_amount = payment.amount
        existing.customer = payment.sale.customer
        existing.notes = (
            f"Customer payment #{payment.id} (Sale #{payment.sale_id})"
        )
        existing.save(update_fields=["total_amount", "customer", "notes"])
        LedgerEntry.objects.filter(transaction=existing).delete()
        _create_ledger_entries(existing, ledger_rows)
        return existing

    txn = InventoryTransaction.objects.create(
        transaction_type=InventoryTransaction.TransactionType.PAYMENT,
        status=InventoryTransaction.TransactionStatus.POSTED,
        customer=payment.sale.customer,
        notes=f"Customer payment #{payment.id} (Sale #{payment.sale_id})",
        source_ref=source_ref,
        total_amount=payment.amount,
    )
    _create_ledger_entries(txn, ledger_rows)
    CustomerPayment.objects.filter(pk=payment.pk).update(inventory_transaction=txn)
    return txn


def delete_payment_ledger(payment):
    """Remove ledger transaction linked to a payment record if present."""
    txn_id = getattr(payment, "inventory_transaction_id", None)
    if not txn_id:
        return
    InventoryTransaction.objects.filter(pk=txn_id).delete()
    type(payment).objects.filter(pk=payment.pk).update(inventory_transaction=None)


def format_source_ref(source_ref, *, transaction_type=None, transaction_id=None):
    """Human-readable label for stock ledger references."""
    ref = (source_ref or "").strip()
    if not ref:
        if transaction_id:
            return f"Transaction #{transaction_id}"
        return "—"

    if ref.startswith("purchase:"):
        pk = ref.split(":", 1)[1]
        return f"Purchase #{pk}" if pk.isdigit() else f"Purchase ({pk})"
    if ref.startswith("sale:") or (
        transaction_type == InventoryTransaction.TransactionType.SALE
    ):
        if ref.startswith("sale:"):
            pk = ref.split(":", 1)[1]
            return f"Sale #{pk}" if pk.isdigit() else f"Sale ({pk})"
        if transaction_id:
            return f"Sale #{transaction_id}"
    if ref.startswith("vendor_payment:"):
        pk = ref.split(":", 1)[1]
        return f"Supplier payment #{pk}" if pk.isdigit() else "Supplier payment"
    if ref.startswith("customer_payment:"):
        pk = ref.split(":", 1)[1]
        return f"Customer payment #{pk}" if pk.isdigit() else "Customer payment"
    if ref.startswith("adjustment:manual:"):
        return "Manual stock adjustment"
    if ref.startswith("adjustment:item:"):
        return "Stock adjustment"
    if ref.startswith("adjustment:"):
        return "Stock adjustment"
    if ref.startswith("txn:"):
        pk = ref.split(":", 1)[1]
        return f"Transaction #{pk}" if pk.isdigit() else "Transaction"
    return ref


def get_stock_ledger_rows(*, item=None, date_from=None, date_to=None):
    queryset = StockMovement.objects.select_related(
        "item",
        "transaction",
        "transaction__legacy_sale",
        "transaction__legacy_purchase",
    ).order_by("created_at", "id")
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
        txn = move.transaction
        ref = txn.source_ref
        if not ref:
            from django.core.exceptions import ObjectDoesNotExist

            try:
                ref = f"sale:{txn.legacy_sale.pk}"
            except ObjectDoesNotExist:
                try:
                    ref = f"purchase:{txn.legacy_purchase.pk}"
                except ObjectDoesNotExist:
                    ref = ""
        rows.append(
            {
                "created_at": move.created_at,
                "item": move.item,
                "movement_type": move.movement_type,
                "quantity": move.quantity,
                "source_ref": format_source_ref(
                    ref,
                    transaction_type=txn.transaction_type,
                    transaction_id=txn.id,
                ),
                "running_qty": running_totals[key],
            }
        )
    return rows


def get_payables_aging():
    """
    Vendors with outstanding purchase balances, plus stock on hand and last purchase date.
    """
    outstanding_subq = (
        Purchase.objects.filter(
            vendor_id=OuterRef("pk"),
            amount_remaining__gt=0,
        )
        .values("vendor_id")
        .annotate(total=Sum("amount_remaining"))
        .values("total")[:1]
    )
    last_txn_subq = (
        Purchase.objects.filter(vendor_id=OuterRef("pk"))
        .order_by("-order_date")
        .values("order_date")[:1]
    )
    stock_qty_subq = (
        Item.objects.filter(vendor_id=OuterRef("pk"))
        .values("vendor_id")
        .annotate(total=Sum("quantity"))
        .values("total")[:1]
    )
    stock_value_subq = (
        Item.objects.filter(vendor_id=OuterRef("pk"))
        .annotate(
            line_value=ExpressionWrapper(
                F("quantity") * F("cost_price"),
                output_field=DecimalField(max_digits=14, decimal_places=2),
            )
        )
        .values("vendor_id")
        .annotate(total=Sum("line_value"))
        .values("total")[:1]
    )
    zero = Value(0, output_field=DecimalField(max_digits=12, decimal_places=2))
    return (
        Vendor.objects.annotate(
            total_outstanding=Coalesce(
                Subquery(outstanding_subq, output_field=DecimalField(max_digits=12, decimal_places=2)),
                zero,
            ),
            last_transaction_date=Subquery(last_txn_subq),
            total_stock=Coalesce(Subquery(stock_qty_subq), Value(0)),
            total_stock_value=Coalesce(
                Subquery(stock_value_subq, output_field=DecimalField(max_digits=14, decimal_places=2)),
                zero,
            ),
            balance_due=ExpressionWrapper(
                F("total_outstanding") + F("payables_adjustment"),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            ),
        )
        .filter(total_outstanding__gt=0)
        .order_by("-balance_due")
    )


def _vendor_stock_stats(vendor_id):
    stock_qty = (
        Item.objects.filter(vendor_id=vendor_id).aggregate(total=Sum("quantity"))["total"] or 0
    )
    stock_value = Item.objects.filter(vendor_id=vendor_id).aggregate(
        total=Sum(
            ExpressionWrapper(
                F("quantity") * F("cost_price"),
                output_field=DecimalField(max_digits=14, decimal_places=2),
            )
        )
    )["total"] or Decimal("0")
    return {"total_stock": int(stock_qty), "total_stock_value": _to_decimal(stock_value)}


def _purchase_last_transaction_date(purchase):
    last_payment = purchase.vendor_payments.aggregate(last_paid=Max("paid_at"))["last_paid"]
    if last_payment:
        return last_payment
    if purchase.receipt_date:
        return purchase.receipt_date
    return purchase.order_date


def get_payables_aging_report():
    """
    Outstanding purchases grouped by vendor for the payables aging report.
    """
    purchases = (
        Purchase.objects.filter(amount_remaining__gt=0)
        .select_related("vendor")
        .prefetch_related("vendor_payments")
        .order_by("vendor__name", "-order_date")
    )
    by_vendor = {}
    for purchase in purchases:
        vendor = purchase.vendor
        if vendor.id not in by_vendor:
            stats = _vendor_stock_stats(vendor.id)
            adjustment = _to_decimal(vendor.payables_adjustment)
            by_vendor[vendor.id] = {
                "vendor": vendor,
                "bills": [],
                "total_stock": stats["total_stock"],
                "total_stock_value": stats["total_stock_value"],
                "payables_adjustment": adjustment,
                "adjustment_sign": "+" if adjustment >= 0 else "-",
                "adjustment_amount": abs(adjustment),
            }
        by_vendor[vendor.id]["bills"].append(
            {
                "purchase": purchase,
                "bill_number": purchase.display_bill_number,
                "billed_date": purchase.order_date,
                "last_transaction_date": _purchase_last_transaction_date(purchase),
                "outstanding": _to_decimal(purchase.amount_remaining),
            }
        )

    groups = []
    for group in by_vendor.values():
        group["total_outstanding"] = sum(b["outstanding"] for b in group["bills"])
        group["balance_due"] = group["total_outstanding"] + group["payables_adjustment"]
        groups.append(group)
    groups.sort(key=lambda g: g["balance_due"], reverse=True)
    return groups


def allocate_vendor_credit_to_purchases(vendor, credit_amount):
    """Apply payables credit to oldest outstanding purchase bills."""
    remaining = abs(_to_decimal(credit_amount))
    if remaining <= 0:
        return Decimal("0")
    applied = Decimal("0")
    purchases = (
        Purchase.objects.filter(vendor=vendor)
        .order_by("order_date", "id")
        .prefetch_related("vendor_payments")
    )
    for purchase in purchases:
        if remaining <= 0:
            break
        if purchase.amount_paid > 0 and not purchase.vendor_payments.exists():
            VendorPayment.objects.create(
                purchase=purchase,
                amount=purchase.amount_paid,
                method="cash",
                notes="Recorded payment",
            )
        purchase.save()
        outstanding = _to_decimal(purchase.amount_remaining)
        if outstanding <= 0:
            continue
        pay = min(remaining, outstanding)
        VendorPayment.objects.create(
            purchase=purchase,
            amount=pay,
            method="cash",
            notes="Payables book credit",
        )
        applied += pay
        remaining -= pay
    return applied


def update_vendor_payables_adjustment(vendor_id, amount, sign="+"):
    """Persist a manual payables adjustment (+ sets balance owed, − applies credit)."""
    vendor = Vendor.objects.get(pk=vendor_id)
    value = abs(_to_decimal(amount))
    if sign == "-":
        applied = allocate_vendor_credit_to_purchases(vendor, value)
        remainder = value - applied
        if remainder > 0:
            vendor.payables_adjustment = _to_decimal(vendor.payables_adjustment) - remainder
    else:
        vendor.payables_adjustment = value
    vendor.save(update_fields=["payables_adjustment"])
    return vendor


@db_transaction.atomic
def process_purchase_return(purchase, line_returns, *, reason="", user=None):
    """
    Return quantities from a purchase: stock out, bill credit, return history.
    line_returns: list of dicts {line_id, return_qty}.
    """
    from store.stock_adjust import apply_manual_stock_adjustment
    from transactions.models import PurchaseReturn, PurchaseReturnLine

    if not purchase.pk:
        raise ValueError("Purchase must be saved.")
    total_credit = Decimal("0")
    reason_text = (reason or "").strip() or f"Return for {purchase.display_bill_number}"
    return_lines = []

    for entry in line_returns:
        line_id = entry.get("line_id")
        return_qty = int(entry.get("return_qty") or 0)
        if return_qty <= 0:
            continue
        line = purchase.lines.filter(pk=line_id).select_related("item").first()
        if not line:
            continue
        if return_qty > line.quantity:
            raise ValueError(
                f"Cannot return {return_qty} of {line.item.name}; purchased {line.quantity}."
            )
        apply_manual_stock_adjustment(
            line.item,
            mode="remove",
            quantity=return_qty,
            reason=f"{reason_text} (PUR-{purchase.id})",
            user=user,
        )
        line_credit = _to_decimal(line.unit_price) * Decimal(str(return_qty))
        total_credit += line_credit
        line.quantity -= return_qty
        line.save()
        return_lines.append((line, return_qty, line_credit))

    if total_credit <= 0:
        return total_credit

    purchase_return = PurchaseReturn.objects.create(
        purchase=purchase,
        reason=reason_text,
        total_credit=total_credit,
        created_by=user if user and user.is_authenticated else None,
    )
    for line, qty, credit in return_lines:
        PurchaseReturnLine.objects.create(
            purchase_return=purchase_return,
            purchase_line=line,
            quantity=qty,
            unit_price=line.unit_price,
            line_credit=credit,
        )

    purchase.save()

    vendor = Vendor.objects.select_for_update().get(pk=purchase.vendor_id)
    vendor.payables_adjustment = _to_decimal(vendor.payables_adjustment) - total_credit
    vendor.save(update_fields=["payables_adjustment"])
    return total_credit


@db_transaction.atomic
def process_sale_return(sale, line_returns, *, reason="", user=None):
    """
    Return quantities from a sale: restore stock, reduce bill totals, log history.
    line_returns: list of dicts {detail_id, return_qty}.
    """
    from store.stock_adjust import apply_manual_stock_adjustment
    from transactions.models import SaleReturn, SaleReturnLine

    if not sale.pk:
        raise ValueError("Sale must be saved.")
    total_credit = Decimal("0")
    reason_text = (reason or "").strip() or f"Return for sale #{sale.id}"
    return_lines = []
    affected_items = []

    for entry in line_returns:
        detail_id = entry.get("detail_id")
        return_qty = int(entry.get("return_qty") or 0)
        if return_qty <= 0:
            continue
        detail = sale.saledetail_set.filter(pk=detail_id).select_related(
            "item", "variation"
        ).first()
        if not detail:
            continue
        if return_qty > detail.quantity:
            raise ValueError(
                f"Cannot return {return_qty} of {detail.item.name}; sold {detail.quantity}."
            )
        if detail.variation_id:
            variation = detail.variation
            variation.quantity = int(variation.quantity or 0) + return_qty
            variation.save(update_fields=["quantity"])
            affected_items.append(detail.item)
        else:
            apply_manual_stock_adjustment(
                detail.item,
                mode="add",
                quantity=return_qty,
                reason=f"{reason_text} (SALE-{sale.id})",
                user=user,
            )
            affected_items.append(detail.item)

        line_credit = _to_decimal(detail.price) * Decimal(str(return_qty))
        total_credit += line_credit
        detail.quantity -= return_qty
        detail.total_detail = _to_decimal(detail.price) * Decimal(str(detail.quantity))
        detail.save()
        return_lines.append((detail, return_qty, line_credit))

    if total_credit <= 0:
        return total_credit

    sale_return = SaleReturn.objects.create(
        sale=sale,
        reason=reason_text,
        total_credit=total_credit,
        created_by=user if user and user.is_authenticated else None,
    )
    for detail, qty, credit in return_lines:
        SaleReturnLine.objects.create(
            sale_return=sale_return,
            sale_detail=detail,
            quantity=qty,
            unit_price=detail.price,
            line_credit=credit,
        )

    sub_total = Decimal("0")
    for detail in sale.saledetail_set.all():
        sub_total += _to_decimal(detail.total_detail)
    sale.sub_total = sub_total
    tax_pct = Decimal(str(sale.tax_percentage or 0))
    if tax_pct > 0:
        sale.tax_amount = (sub_total * (tax_pct / Decimal("100"))).quantize(
            Decimal("0.01")
        )
    sale.grand_total = sale.sub_total + _to_decimal(sale.tax_amount)
    sale.amount_change = _to_decimal(sale.amount_paid) - sale.grand_total
    sale.save()

    if affected_items:
        sync_item_quantity_cache(affected_items)
    return total_credit


def create_payable_quick_entry(
    vendor,
    *,
    bill_number="",
    order_date=None,
    net_amount=0,
    amount_paid=0,
    description="",
    payment_method="cash",
):
    """
    Create a purchase bill for the payables book (no stock posted until marked Received).
    """
    amount_paid_dec = _to_decimal(amount_paid)
    purchase = Purchase(
        vendor=vendor,
        bill_number=(bill_number or "").strip(),
        order_date=order_date or timezone.now(),
        quantity=1,
        price=_to_decimal(net_amount),
        discount_amount=Decimal("0"),
        vat_percentage=0,
        vat_amount=Decimal("0"),
        amount_paid=Decimal("0"),
        receipt_status="P",
        description=(description or "").strip() or None,
    )
    purchase.save()
    if amount_paid_dec > 0:
        VendorPayment.objects.create(
            purchase=purchase,
            amount=amount_paid_dec,
            method=payment_method if payment_method in ("cash", "bank") else "cash",
        )
        purchase.refresh_from_db()
    return purchase
