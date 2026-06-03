"""
Module: store.views

Contains Django views for managing items, profiles,
and deliveries in the store application.

Classes handle product listing, creation, updating,
deletion, and delivery management.
The module integrates with Django's authentication
and querying functionalities.
"""

# Standard library imports
import logging
import operator
from decimal import Decimal
from functools import reduce

logger = logging.getLogger(__name__)

# Django core imports
from django.shortcuts import render
from django.urls import reverse, reverse_lazy
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Q, Count, Sum

# Authentication and permissions
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin

# Class-based views
from django.views.generic import (
    DetailView, CreateView, UpdateView, DeleteView, ListView
)

# Third-party packages
from django_tables2 import SingleTableView
import django_tables2 as tables
from django_tables2.export.views import ExportMixin

# Local app imports
from accounts.models import Vendor, Customer
from transactions.models import Sale, SaleDetail, Purchase
from .models import Category, Item, Delivery, ProductVariation
from .forms import ItemForm, CategoryForm, DeliveryForm, ProductVariationFormSet
from .tables import ItemTable
from .filters import ProductFilter, DeliveryFilter
from .stock_utils import build_item_stock_map, get_variant_stock_total
from transactions.services import reconcile_ledger_stock_to_target, sync_item_quantity_cache


@login_required
def dashboard(request):
    from django.utils import timezone
    from datetime import timedelta
    
    Category.objects.annotate(nitem=Count("item"))
    items = list(Item.objects.all())
    item_stock_by_id = build_item_stock_map(items)
    total_items = sum(item_stock_by_id.values())
    items_count = len(items)
    
    # Sales statistics
    sales = Sale.objects.all()
    total_revenue = sales.aggregate(Sum("grand_total")).get("grand_total__sum") or 0
    today_sales = sales.filter(date_added__date=timezone.now().date())
    today_revenue = today_sales.aggregate(Sum("grand_total")).get("grand_total__sum") or 0
    
    # This month sales
    start_of_month = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_sales = sales.filter(date_added__gte=start_of_month)
    month_revenue = month_sales.aggregate(Sum("grand_total")).get("grand_total__sum") or 0
    
    # Customers
    customers_count = Customer.objects.count()
    
    # Vendors
    vendors_count = Vendor.objects.count()
    
    # Purchases
    purchases = Purchase.objects.all()
    total_purchases = purchases.aggregate(Sum("total_value")).get("total_value__sum") or 0
    
    # Low stock items (ledger on-hand vs threshold)
    low_stock_items_list = []
    for item in items:
        item.current_stock = item_stock_by_id.get(item.id, item.quantity)
        if item.current_stock <= item.low_stock_threshold:
            low_stock_items_list.append(item)
    low_stock_items = len(low_stock_items_list)
    
    # Calculate profit statistics (coerce floats to Decimal for sale line prices)
    total_cost = sum(
        Decimal(str(item.cost_price or 0))
        * item_stock_by_id.get(item.id, item.quantity)
        for item in items
        if item.cost_price and item.cost_price > 0
    )
    total_profit = Decimal("0")
    for sale in sales:
        for detail in sale.saledetail_set.all():
            item_cost = (
                Decimal(str(detail.item.cost_price))
                if detail.item.cost_price and detail.item.cost_price > 0
                else Decimal("0")
            )
            total_profit += (detail.price - item_cost) * detail.quantity
    
    # Recent sales (last 5)
    recent_sales = sales.order_by('-date_added')[:5]
    
    # Recent purchases (last 5)
    recent_purchases = purchases.order_by('-order_date')[:5]
    
    # Top selling products (by quantity sold)
    from django.db.models import Sum as DjangoSum
    top_products = (
        SaleDetail.objects.values('item__name')
        .annotate(total_sold=DjangoSum('quantity'))
        .order_by('-total_sold')[:5]
    )

    # Prepare data for charts
    category_counts = Category.objects.annotate(
        item_count=Count("item")
    ).values("name", "item_count")
    categories = [cat["name"] for cat in category_counts]
    category_counts = [cat["item_count"] for cat in category_counts]

    # Sales over time (last 7 days)
    seven_days_ago = timezone.now() - timedelta(days=7)
    sale_dates = (
        Sale.objects.filter(date_added__gte=seven_days_ago)
        .values("date_added__date")
        .annotate(total_sales=Sum("grand_total"))
        .order_by("date_added__date")
    )
    sale_dates_labels = [
        date["date_added__date"].strftime("%Y-%m-%d") for date in sale_dates
    ]
    sale_dates_values = [float(date["total_sales"]) for date in sale_dates]
    
    # If no sales data, add empty arrays
    if not sale_dates_labels:
        sale_dates_labels = []
        sale_dates_values = []

    context = {
        "items": items,
        "items_count": items_count,
        "total_items": total_items,
        "vendors": Vendor.objects.all(),
        "vendors_count": vendors_count,
        "delivery": Delivery.objects.all(),
        "sales": sales,
        "sales_count": sales.count(),
        "total_revenue": total_revenue,
        "today_revenue": today_revenue,
        "month_revenue": month_revenue,
        "customers_count": customers_count,
        "total_purchases": total_purchases,
        "low_stock_items": low_stock_items,
        "low_stock_items_list": low_stock_items_list[:10],  # Show top 10 low stock items
        "total_profit": total_profit,
        "total_cost": total_cost,
        "recent_sales": recent_sales,
        "recent_purchases": recent_purchases,
        "top_products": top_products,
        "categories": categories,
        "category_counts": category_counts,
        "sale_dates_labels": sale_dates_labels,
        "sale_dates_values": sale_dates_values,
    }
    return render(request, "store/dashboard.html", context)


class ProductListView(LoginRequiredMixin, ExportMixin, tables.SingleTableView):
    """
    View class to display a list of products with filtering.

    Attributes:
    - model: The model associated with the view.
    - table_class: The table class used for rendering.
    - template_name: The HTML template used for rendering the view.
    - context_object_name: The variable name for the context object.
    - paginate_by: Number of items per page for pagination.
    """

    model = Item
    table_class = ItemTable
    template_name = "store/productslist.html"
    context_object_name = "items"
    paginate_by = 10
    SingleTableView.table_pagination = False
    filterset_class = ProductFilter

    def get_queryset(self):
        queryset = super().get_queryset().prefetch_related('variations')
        self.filterset = self.filterset_class(self.request.GET, queryset=queryset)
        return self.filterset.qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter'] = self.filterset
        items = list(context.get('items') or context.get('object_list') or [])
        stock_map = build_item_stock_map(items)
        for item in items:
            item.current_stock = stock_map.get(item.id, item.quantity)
        return context


class ItemSearchListView(ProductListView):
    """
    View class to search and display a filtered list of items.

    Attributes:
    - paginate_by: Number of items per page for pagination.
    """

    paginate_by = 10

    def get_queryset(self):
        result = super(ItemSearchListView, self).get_queryset()

        query = self.request.GET.get("q")
        if query:
            query_list = query.split()
            result = result.filter(
                reduce(
                    operator.and_, (Q(name__icontains=q) for q in query_list)
                )
            )
        return result


class ProductDetailView(LoginRequiredMixin, DetailView):
    """
    View class to display detailed information about a product.

    Attributes:
    - model: The model associated with the view.
    - template_name: The HTML template used for rendering the view.
    """

    model = Item
    template_name = "store/productdetail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['variations'] = self.object.variations.all()
        return context

    def get_success_url(self):
        return reverse("product-detail", kwargs={"slug": self.object.slug})


class ProductCreateView(LoginRequiredMixin, CreateView):
    """
    View class to create a new product.

    Attributes:
    - model: The model associated with the view.
    - template_name: The HTML template used for rendering the view.
    - form_class: The form class used for data input.
    - success_url: The URL to redirect to upon successful form submission.
    """

    model = Item
    template_name = "store/productcreate.html"
    form_class = ItemForm
    success_url = reverse_lazy("productslist")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['variation_formset'] = ProductVariationFormSet(
                self.request.POST,
                self.request.FILES
            )
        else:
            context['variation_formset'] = ProductVariationFormSet()
        return context

    def _sync_product_stock(self, item, form):
        variant_total = get_variant_stock_total(item)
        desired_total = int(form.cleaned_data.get("quantity") or 0)
        ledger_target = max(0, desired_total - variant_total)
        reconcile_ledger_stock_to_target(
            item, ledger_target, notes=f"Product create #{item.pk}"
        )
        sync_item_quantity_cache([item])

    def form_valid(self, form):
        context = self.get_context_data()
        variation_formset = context['variation_formset']
        
        if variation_formset.is_valid():
            self.object = form.save()
            variation_formset.instance = self.object
            variation_formset.save()
            self._sync_product_stock(self.object, form)
            return super().form_valid(form)
        else:
            return self.form_invalid(form)

    def test_func(self):
        # item = Item.objects.get(id=pk)
        if self.request.POST.get("quantity") < 1:
            return False
        else:
            return True


class ProductUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    """
    View class to update product information.

    Attributes:
    - model: The model associated with the view.
    - template_name: The HTML template used for rendering the view.
    - fields: The fields to be updated.
    - success_url: The URL to redirect to upon successful form submission.
    """

    model = Item
    template_name = "store/productupdate.html"
    form_class = ItemForm
    success_url = reverse_lazy("productslist")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['variation_formset'] = ProductVariationFormSet(
                self.request.POST,
                self.request.FILES,
                instance=self.object
            )
        else:
            context['variation_formset'] = ProductVariationFormSet(
                instance=self.object
            )
        return context

    def _sync_product_stock(self, item, form):
        variant_total = get_variant_stock_total(item)
        desired_total = int(form.cleaned_data.get("quantity") or 0)
        ledger_target = max(0, desired_total - variant_total)
        reconcile_ledger_stock_to_target(
            item, ledger_target, notes=f"Product update #{item.pk}"
        )
        sync_item_quantity_cache([item])

    def form_valid(self, form):
        context = self.get_context_data()
        variation_formset = context['variation_formset']
        
        if variation_formset.is_valid():
            self.object = form.save()
            variation_formset.instance = self.object
            variation_formset.save()
            self._sync_product_stock(self.object, form)
            return super().form_valid(form)
        else:
            return self.form_invalid(form)

    def test_func(self):
        if self.request.user.is_superuser:
            return True
        profile = getattr(self.request.user, "profile", None)
        return profile is not None and getattr(profile, "role", None) == "AD"


class ProductDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    """
    View class to delete a product.

    Attributes:
    - model: The model associated with the view.
    - template_name: The HTML template used for rendering the view.
    - success_url: The URL to redirect to upon successful deletion.
    """

    model = Item
    template_name = "store/productdelete.html"
    success_url = reverse_lazy("productslist")

    def test_func(self):
        if self.request.user.is_superuser:
            return True
        else:
            return False


class DeliveryListView(
    LoginRequiredMixin, ExportMixin, tables.SingleTableView
):
    """
    View class to display a list of deliveries.

    Attributes:
    - model: The model associated with the view.
    - pagination: Number of items per page for pagination.
    - template_name: The HTML template used for rendering the view.
    - context_object_name: The variable name for the context object.
    """

    model = Delivery
    pagination = 10
    template_name = "store/deliveries.html"
    context_object_name = "deliveries"


class DeliverySearchListView(DeliveryListView):
    """
    View class to search and display a filtered list of deliveries.

    Attributes:
    - paginate_by: Number of items per page for pagination.
    """

    paginate_by = 10

    def get_queryset(self):
        result = super(DeliverySearchListView, self).get_queryset()

        query = self.request.GET.get("q")
        if query:
            query_list = query.split()
            result = result.filter(
                reduce(
                    operator.
                    and_, (Q(customer_name__icontains=q) for q in query_list)
                )
            )
        return result


class DeliveryDetailView(LoginRequiredMixin, DetailView):
    """
    View class to display detailed information about a delivery.

    Attributes:
    - model: The model associated with the view.
    - template_name: The HTML template used for rendering the view.
    """

    model = Delivery
    template_name = "store/deliverydetail.html"


class DeliveryCreateView(LoginRequiredMixin, CreateView):
    """
    View class to create a new delivery.

    Attributes:
    - model: The model associated with the view.
    - fields: The fields to be included in the form.
    - template_name: The HTML template used for rendering the view.
    - success_url: The URL to redirect to upon successful form submission.
    """

    model = Delivery
    form_class = DeliveryForm
    template_name = "store/delivery_form.html"
    success_url = reverse_lazy("deliveries")


class DeliveryUpdateView(LoginRequiredMixin, UpdateView):
    """
    View class to update delivery information.

    Attributes:
    - model: The model associated with the view.
    - fields: The fields to be updated.
    - template_name: The HTML template used for rendering the view.
    - success_url: The URL to redirect to upon successful form submission.
    """

    model = Delivery
    form_class = DeliveryForm
    template_name = "store/delivery_form.html"
    success_url = reverse_lazy("deliveries")


class DeliveryDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    """
    View class to delete a delivery.

    Attributes:
    - model: The model associated with the view.
    - template_name: The HTML template used for rendering the view.
    - success_url: The URL to redirect to upon successful deletion.
    """

    model = Delivery
    template_name = "store/productdelete.html"
    success_url = reverse_lazy("deliveries")

    def test_func(self):
        if self.request.user.is_superuser:
            return True
        else:
            return False


class CategoryListView(LoginRequiredMixin, ListView):
    model = Category
    template_name = 'store/category_list.html'
    context_object_name = 'categories'
    paginate_by = 10
    login_url = 'login'


class CategoryDetailView(LoginRequiredMixin, DetailView):
    model = Category
    template_name = 'store/category_detail.html'
    context_object_name = 'category'
    login_url = 'login'


class CategoryCreateView(LoginRequiredMixin, CreateView):
    model = Category
    template_name = 'store/category_form.html'
    form_class = CategoryForm
    login_url = 'login'

    def get_success_url(self):
        return reverse_lazy('category-detail', kwargs={'pk': self.object.pk})


class CategoryUpdateView(LoginRequiredMixin, UpdateView):
    model = Category
    template_name = 'store/category_form.html'
    form_class = CategoryForm
    login_url = 'login'

    def get_success_url(self):
        return reverse_lazy('category-detail', kwargs={'pk': self.object.pk})


class CategoryDeleteView(LoginRequiredMixin, DeleteView):
    model = Category
    template_name = 'store/category_confirm_delete.html'
    context_object_name = 'category'
    success_url = reverse_lazy('category-list')
    login_url = 'login'


def is_ajax(request):
    return request.META.get('HTTP_X_REQUESTED_WITH') == 'XMLHttpRequest'


@csrf_exempt
@require_POST
@login_required
def get_items_ajax_view(request):
    try:
        term = (request.POST.get("term") or "").strip()
        data = []
        qs = Item.objects.select_related("category", "vendor").prefetch_related(
            "variations"
        )
        if term:
            qs = qs.filter(name__icontains=term)
        for item in qs.order_by("name")[:20]:
            try:
                data.append(item.to_json())
            except Exception as exc:
                logger.error("Error serializing item %s: %s", item.id, exc)
        return JsonResponse(data, safe=False)
    except Exception as exc:
        logger.error("Error in get_items_ajax_view: %s", exc)
        return JsonResponse({"error": str(exc)}, status=500)
