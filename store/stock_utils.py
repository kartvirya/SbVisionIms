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
            result[item.id] = 0
    return result


def build_item_stock_map(items):
    """Ledger on-hand plus variant quantities for each item."""
    ledger = build_ledger_stock_map(items)
    return {
        item.id: ledger.get(item.id, 0) + get_variant_stock_total(item) for item in items
    }


def get_ledger_stock(item):
    """Base stock from inventory movements (excludes variant-only qty)."""
    return build_ledger_stock_map([item]).get(item.id, 0)


def get_item_current_stock(item):
    """Total sellable/display stock: ledger + active variants."""
    return get_ledger_stock(item) + get_variant_stock_total(item)


def get_sellable_stock(item, variation_id=None):
    """
    Stock available for a sale line.
    Variant sales use that variant's quantity; base sales use ledger only
    (variant pools are not sold without selecting a variant).
    """
    if variation_id:
        from store.models import ProductVariation

        variation = ProductVariation.objects.filter(
            pk=variation_id, item=item, is_active=True
        ).first()
        if variation:
            return int(variation.quantity or 0)
        return 0
    return get_ledger_stock(item)


def set_item_total_stock(item, target_total, *, notes="Stock adjustment"):
    """
    Set combined ledger + active variant stock to target_total.
    Returns (quantity_before, quantity_after).
    """
    from store.models import ProductVariation
    from transactions.services import reconcile_ledger_stock_to_target, sync_item_quantity_cache

    target = max(0, int(target_total))
    variants = list(
        ProductVariation.objects.filter(item=item, is_active=True).order_by("id")
    )
    variant_total = sum(int(v.quantity or 0) for v in variants)
    before = get_ledger_stock(item) + variant_total

    if target == before:
        sync_item_quantity_cache([item])
        return before, before

    if not variants:
        reconcile_ledger_stock_to_target(item, target, notes=notes)
        sync_item_quantity_cache([item])
        return before, target

    reconcile_ledger_stock_to_target(item, 0, notes=notes)

    if target == 0:
        for variation in variants:
            if int(variation.quantity or 0) != 0:
                variation.quantity = 0
                variation.save(update_fields=["quantity"])
    elif variant_total <= 0:
        variants[0].quantity = target
        variants[0].save(update_fields=["quantity"])
    elif target > variant_total:
        reconcile_ledger_stock_to_target(
            item, target - variant_total, notes=notes
        )
    else:
        remaining = target
        for index, variation in enumerate(variants):
            old_qty = int(variation.quantity or 0)
            if index == len(variants) - 1:
                new_qty = remaining
            elif variant_total > 0:
                new_qty = int(round(target * old_qty / variant_total))
                new_qty = min(new_qty, remaining)
                remaining -= new_qty
            else:
                new_qty = 0
            variation.quantity = new_qty
            variation.save(update_fields=["quantity"])

    sync_item_quantity_cache([item])
    after = get_item_current_stock(item)
    return before, after
