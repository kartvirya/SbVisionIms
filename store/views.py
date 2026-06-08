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
from django.shortcuts import render, get_object_or_404
from django.urls import reverse, reverse_lazy
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Q, Count, Sum

# Authentication and permissions
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db import transaction
from django.shortcuts import redirect as auth_redirect

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
from .forms import (
    ItemForm,
    CategoryForm,
    DeliveryForm,
    ProductVariationFormSet,
    StockAdjustmentForm,
)
from .import_utils import (
    IMPORT_HANDLERS,
    IMPORT_HEADERS,
    TEMPLATE_BUILDERS,
    read_sheet_rows,
)
from .stock_adjust import apply_manual_stock_adjustment
from .tables import ItemTable
from .filters import ProductFilter, DeliveryFilter
from .list_display import annotate_list_row_numbers
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
        qs = self.filterset.qs
        if not self.request.GET.get("ordering"):
            qs = qs.order_by("-id")
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter'] = self.filterset
        items = list(context.get('items') or context.get('object_list') or [])
        stock_map = build_item_stock_map(items)
        for item in items:
            item.current_stock = stock_map.get(item.id, item.quantity)
        annotate_list_row_numbers(items, context.get("page_obj"))
        context["can_manage_products"] = user_can_manage_products(self.request.user)
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


def _redirect_after_stock_adjust(request, item, default_url=None):
    next_url = (request.POST.get("next") or default_url or item.get_absolute_url()).strip()
    if next_url.startswith("/"):
        return auth_redirect(next_url)
    return auth_redirect(item.get_absolute_url())


def _apply_stock_adjustment_request(request, item):
    form = StockAdjustmentForm(item, request.POST)
    if not form.is_valid():
        messages.error(request, "Please correct the stock adjustment form.")
        return False
    try:
        apply_manual_stock_adjustment(
            item,
            mode=form.cleaned_data["mode"],
            quantity=form.cleaned_data["quantity"],
            reason=form.cleaned_data.get("reason", ""),
            user=request.user,
            variation=form.cleaned_data.get("variation"),
        )
        messages.success(request, f"Stock updated for {item.name}.")
        return True
    except ValueError as exc:
        messages.error(request, str(exc))
        return False


@login_required
def stock_adjust_view(request, pk):
    """Adjust stock from inventory list modal or direct link."""
    item = get_object_or_404(
        Item.objects.prefetch_related("variations"), pk=pk
    )
    default_next = reverse("productslist")

    if request.method == "POST":
        _apply_stock_adjustment_request(request, item)
        return _redirect_after_stock_adjust(request, item, default_next)

    stock_map = build_item_stock_map([item])
    context = {
        "item": item,
        "stock_form": StockAdjustmentForm(item),
        "current_stock": stock_map.get(item.id, item.quantity),
        "next_url": request.GET.get("next") or default_next,
        "modal": request.headers.get("X-Requested-With") == "XMLHttpRequest",
    }
    template = "store/partials/stock_adjust_modal_body.html"
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return render(request, template, context)
    return render(
        request,
        "store/stock_adjust_page.html",
        {**context, "modal": False},
    )


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
        context["variations"] = self.object.variations.filter(is_active=True)
        context["adjustment_logs"] = (
            self.object.adjustment_logs.select_related("variation", "created_by")[:50]
        )
        stock_map = build_item_stock_map([self.object])
        context["current_stock"] = stock_map.get(self.object.id, self.object.quantity)
        context["stock_form"] = StockAdjustmentForm(self.object)
        context["stock_adjust_next"] = self.object.get_absolute_url()
        context["can_manage_products"] = user_can_manage_products(self.request.user)
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


def _item_delete_blockers(item):
    from transactions.models import PurchaseLine, SaleDetail, StockMovement

    blockers = []
    if PurchaseLine.objects.filter(item=item).exists():
        blockers.append("purchase lines")
    if SaleDetail.objects.filter(item=item).exists():
        blockers.append("sales")
    if StockMovement.objects.filter(item=item).exists():
        blockers.append("stock movements")
    if item.adjustment_logs.exists():
        blockers.append("stock adjustments")
    return blockers


def user_can_manage_products(user):
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    profile = getattr(user, "profile", None)
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
        return user_can_manage_products(self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["delete_blockers"] = _item_delete_blockers(self.object)
        return context

    def delete(self, request, *args, **kwargs):
        from django.db import IntegrityError
        from django.db.models.deletion import ProtectedError

        self.object = self.get_object()
        blockers = _item_delete_blockers(self.object)
        if blockers:
            messages.error(
                request,
                "Cannot delete this product — it is linked to "
                + ", ".join(blockers)
                + ".",
            )
            return auth_redirect(self.get_success_url())
        try:
            with transaction.atomic():
                return super().delete(request, *args, **kwargs)
        except (ProtectedError, IntegrityError):
            messages.error(
                request,
                "Cannot delete this product — it is linked to purchases, "
                "sales, or stock movements. Remove those records first.",
            )
            return auth_redirect(self.get_success_url())


class DeliveryListView(LoginRequiredMixin, ListView):
    """
    View class to display a list of deliveries.

    Attributes:
    - model: The model associated with the view.
    - pagination: Number of items per page for pagination.
    - template_name: The HTML template used for rendering the view.
    - context_object_name: The variable name for the context object.
    """

    model = Delivery
    paginate_by = 10
    template_name = "store/deliveries.html"
    context_object_name = "deliveries"
    filterset_class = DeliveryFilter

    def get_queryset(self):
        qs = super().get_queryset().select_related("item", "logistics")
        self.filterset = self.filterset_class(self.request.GET, queryset=qs)
        result = self.filterset.qs
        if not self.request.GET.get("ordering"):
            result = result.order_by("-date", "-id")
        return result

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["filter"] = self.filterset
        annotate_list_row_numbers(
            context.get("deliveries") or [], context.get("page_obj")
        )
        return context


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

    def get_queryset(self):
        return super().get_queryset().order_by("-pk")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        annotate_list_row_numbers(
            list(context.get("categories") or []), context.get("page_obj")
        )
        return context


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
        page = max(int(request.POST.get("page") or 1), 1)
        page_size = 50
        qs = Item.objects.select_related("category", "vendor").prefetch_related(
            "variations"
        )
        if term:
            words = [w for w in term.split() if w]
            for word in words:
                qs = qs.filter(
                    Q(name__icontains=word)
                    | Q(sku__icontains=word)
                    | Q(description__icontains=word)
                    | Q(category__name__icontains=word)
                    | Q(vendor__name__icontains=word)
                )
        qs = qs.order_by("-id", "name")
        offset = (page - 1) * page_size
        page_items = list(qs[offset : offset + page_size + 1])
        has_more = len(page_items) > page_size
        page_items = page_items[:page_size]
        data = []
        for item in page_items:
            try:
                data.append(item.to_json())
            except Exception as exc:
                logger.error("Error serializing item %s: %s", item.id, exc)
        return JsonResponse({"results": data, "more": has_more})
    except Exception as exc:
        logger.error("Error in get_items_ajax_view: %s", exc)
        return JsonResponse({"error": str(exc)}, status=500)


IMPORT_LABELS = {
    "inventory": "Inventory",
    "customers": "Customers",
    "suppliers": "Suppliers",
    "purchases": "Purchase Book",
    "sales": "Sales Book",
    "deliveries": "Deliveries",
    "invoices": "Customer Invoices",
    "bills": "Miscellaneous Bills",
}

IMPORT_REDIRECTS = {
    "inventory": "productslist",
    "customers": "dashboard",
    "suppliers": "vendor-list",
    "purchases": "purchaseslist",
    "sales": "saleslist",
    "deliveries": "deliveries",
    "invoices": "invoicelist",
    "bills": "bill_list",
}


@login_required
def import_data_view(request, kind):
    """Upload Excel/CSV bulk import."""
    if kind not in IMPORT_HANDLERS:
        messages.error(request, "Unknown import type.")
        return auth_redirect(reverse("dashboard"))

    template_name = "store/import_data.html"
    if request.method == "GET" and request.GET.get("download") == "template":
        wb = TEMPLATE_BUILDERS[kind]()
        filename = f"{kind}_import_template.xlsx"
        response = HttpResponse(
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        wb.save(response)
        return response

    if request.method == "POST":
        upload = request.FILES.get("file")
        if not upload:
            messages.error(request, "Choose a file to upload (.xlsx or .csv).")
        else:
            headers = IMPORT_HEADERS[kind]
            rows, sheet_errors = read_sheet_rows(upload, headers)
            if sheet_errors:
                for err in sheet_errors:
                    messages.error(request, err)
            elif not rows:
                messages.warning(request, "No data rows found in the file.")
            else:
                created, updated, errors = IMPORT_HANDLERS[kind](rows)
                for err in errors[:20]:
                    messages.warning(request, err)
                if errors and len(errors) > 20:
                    messages.warning(
                        request, f"...and {len(errors) - 20} more row errors."
                    )
                messages.success(
                    request,
                    f"Import complete: {created} created, {updated} updated.",
                )
                return auth_redirect(reverse(IMPORT_REDIRECTS.get(kind, "dashboard")))

    context = {
        "kind": kind,
        "kind_label": IMPORT_LABELS.get(kind, kind.title()),
    }
    return render(request, template_name, context)
