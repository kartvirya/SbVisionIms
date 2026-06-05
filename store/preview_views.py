"""HTML partials for the unified preview drawer."""

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render

from store.models import Delivery, Item
from store.stock_utils import build_item_stock_map, get_variant_stock_total
from transactions.models import Purchase, Sale


@login_required
def preview_item(request, pk):
    item = get_object_or_404(
        Item.objects.select_related("category", "vendor"), pk=pk
    )
    stock_map = build_item_stock_map([item])
    return render(
        request,
        "store/previews/item.html",
        {
            "object": item,
            "current_stock": stock_map.get(item.id, item.quantity),
            "variations": item.variations.filter(is_active=True),
            "adjustment_logs": item.adjustment_logs.select_related(
                "variation", "created_by"
            )[:10],
        },
    )


@login_required
def preview_sale(request, pk):
    sale = get_object_or_404(
        Sale.objects.select_related("customer").prefetch_related(
            "saledetail_set__item", "saledetail_set__variation", "customer_payments"
        ),
        pk=pk,
    )
    return render(request, "store/previews/sale.html", {"object": sale})


@login_required
def preview_purchase(request, slug):
    purchase = get_object_or_404(
        Purchase.objects.select_related("vendor").prefetch_related(
            "lines__item", "returns__lines__purchase_line__item", "vendor_payments"
        ),
        slug=slug,
    )
    return render(request, "store/previews/purchase.html", {"object": purchase})


@login_required
def preview_delivery(request, pk):
    delivery = get_object_or_404(
        Delivery.objects.select_related("item", "logistics"), pk=pk
    )
    return render(request, "store/previews/delivery.html", {"object": delivery})
