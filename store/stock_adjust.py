"""Manual stock adjustments with audit log."""

import uuid
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import transaction as db_transaction

from store.models import ProductVariation, StockAdjustmentLog
from transactions.models import InventoryTransaction, InventoryTransactionItem, StockMovement
from transactions.services import sync_item_quantity_cache, _to_decimal

User = get_user_model()

ADJUSTMENT_MODES = ("add", "remove", "set")


def _post_ledger_delta(item, delta, notes):
    """Post a one-off IN/OUT ledger movement (unique source_ref per adjustment)."""
    if delta == 0:
        return None
    movement_type = (
        StockMovement.MovementType.IN if delta > 0 else StockMovement.MovementType.OUT
    )
    qty = abs(int(delta))
    source_ref = f"adjustment:manual:{item.id}:{uuid.uuid4().hex[:12]}"
    txn = InventoryTransaction.objects.create(
        transaction_type=InventoryTransaction.TransactionType.ADJUSTMENT,
        status=InventoryTransaction.TransactionStatus.POSTED,
        notes=notes,
        source_ref=source_ref,
    )
    InventoryTransactionItem.objects.create(
        transaction=txn,
        item=item,
        quantity=Decimal(str(qty)),
        unit_price=Decimal("0"),
        line_total=Decimal("0"),
    )
    StockMovement.objects.create(
        item=item,
        transaction=txn,
        movement_type=movement_type,
        quantity=Decimal(str(qty)),
    )
    txn.total_amount = Decimal("0")
    txn.save(update_fields=["total_amount"])
    return txn


@db_transaction.atomic
def apply_manual_stock_adjustment(
    item,
    *,
    mode,
    quantity,
    reason="",
    user=None,
    variation=None,
):
    """
    Adjust variant qty or ledger stock. mode: add | remove | set.
    Returns StockAdjustmentLog.
    """
    if mode not in ADJUSTMENT_MODES:
        raise ValueError(f"Invalid adjustment mode: {mode}")
    qty = int(quantity)
    if qty < 0:
        raise ValueError("Quantity must be non-negative.")
    if mode != "set" and qty == 0:
        raise ValueError("Quantity must be greater than zero.")

    reason = (reason or "").strip() or "Manual adjustment"
    txn = None

    if variation is not None:
        if variation.item_id != item.id:
            raise ValueError("Variation does not belong to this product.")
        before = int(variation.quantity or 0)
        if mode == "add":
            after = before + qty
        elif mode == "remove":
            after = before - qty
            if after < 0:
                raise ValueError(f"Cannot remove {qty}; only {before} in variant stock.")
        else:
            after = qty
        variation.quantity = after
        variation.save(update_fields=["quantity"])
        sync_item_quantity_cache([item])
        delta = after - before
    else:
        from store.stock_utils import get_ledger_stock

        before = int(get_ledger_stock(item))
        if mode == "add":
            after = before + qty
        elif mode == "remove":
            after = before - qty
            if after < 0:
                raise ValueError(f"Cannot remove {qty}; only {before} in base ledger stock.")
        else:
            after = qty
        delta = after - before
        txn = _post_ledger_delta(item, delta, f"Manual: {reason}")
        sync_item_quantity_cache([item])

    log = StockAdjustmentLog.objects.create(
        item=item,
        variation=variation,
        mode=mode,
        quantity_delta=delta,
        quantity_before=before,
        quantity_after=after,
        reason=reason,
        created_by=user if user and user.is_authenticated else None,
        inventory_transaction=txn,
    )
    return log
