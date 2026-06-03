"""Helpers for on-hand stock from movement ledger and product variants."""

from django.db.models import Sum

from transactions.models import StockMovement


def get_variant_stock_total(item):
    """Sum of active variant quantities (rolled into total on-hand for the product)."""
    from store.models import ProductVariation

    total = (
        ProductVariation.objects.filter(item=item, is_active=True).aggregate(
            t=Sum("quantity")
        )["t"]
    )
    return int(total or 0)


def build_ledger_stock_map(items):
    """
    Return {item_id: ledger_qty} from stock movements only.
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


def build_item_stock_map(items):
    """Ledger on-hand plus variant quantities for each item."""
    ledger = build_ledger_stock_map(items)
    return {
        item.id: ledger.get(item.id, 0) + get_variant_stock_total(item) for item in items
    }


def get_ledger_stock(item):
    """Base stock from inventory movements (excludes variant-only qty)."""
    return build_ledger_stock_map([item]).get(item.id, int(item.quantity or 0))


def get_item_current_stock(item):
    """Total sellable/display stock: ledger + active variants."""
    return get_ledger_stock(item) + get_variant_stock_total(item)


def get_sellable_stock(item, variation_id=None):
    """Stock available for a sale line (variant row or combined total)."""
    if variation_id:
        from store.models import ProductVariation

        variation = ProductVariation.objects.filter(
            pk=variation_id, item=item, is_active=True
        ).first()
        if variation:
            return int(variation.quantity or 0)
    return get_item_current_stock(item)
