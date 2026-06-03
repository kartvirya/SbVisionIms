"""Helpers for on-hand stock from movement ledger."""

from django.db.models import Sum

from transactions.models import StockMovement


def build_item_stock_map(items):
    """
    Return {item_id: on_hand_qty} using stock movements, falling back to Item.quantity.
    """
    item_ids = [item.id for item in items]
    if not item_ids:
        return {}

    movement_sums = (
        StockMovement.objects.filter(item_id__in=item_ids)
        .values("item_id", "movement_type")
        .annotate(total_qty=Sum("quantity"))
    )
    stock_totals = {}
    for row in movement_sums:
        item_id = row["item_id"]
        if item_id not in stock_totals:
            stock_totals[item_id] = {"IN": 0, "OUT": 0}
        stock_totals[item_id][row["movement_type"]] = row["total_qty"] or 0

    result = {}
    for item in items:
        if item.id in stock_totals:
            totals = stock_totals[item.id]
            result[item.id] = int(totals.get("IN", 0) - totals.get("OUT", 0))
        else:
            result[item.id] = int(item.quantity or 0)
    return result


def get_item_current_stock(item):
    """On-hand quantity for one item."""
    return build_item_stock_map([item]).get(item.id, int(item.quantity or 0))
