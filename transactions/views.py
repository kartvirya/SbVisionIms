# Standard library imports
import json
import logging
from decimal import Decimal

# Django core imports
from django.http import JsonResponse, HttpResponse, HttpResponseRedirect
from django.urls import reverse
from django.shortcuts import render
from django.db import transaction
from django.contrib import messages

# Class-based views
from django.views.generic import DetailView, ListView
from django.views.generic.edit import CreateView, UpdateView, DeleteView

# Authentication and permissions
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin

# Third-party packages
from openpyxl import Workbook

# Local app imports
from store.models import Item
from accounts.models import Customer, Company
from .models import CustomerPayment, Purchase, Sale, SaleDetail
from .forms import PurchaseForm, PurchaseLineFormSet
from .filters import SaleFilter, PurchaseFilter
from .services import (
    create_sale_transaction,
    delete_inventory_transaction_and_sync,
    get_payables_aging,
    get_stock_ledger_rows,
    sync_purchase_inventory_transaction,
)


logger = logging.getLogger(__name__)


def is_ajax(request):
    return request.META.get('HTTP_X_REQUESTED_WITH') == 'XMLHttpRequest'


def export_sales_to_excel(request):
    # Create a workbook and select the active worksheet.
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = 'Sales'

    # Define the column headers
    columns = [
        'ID', 'Date', 'Customer', 'Sub Total',
        'Grand Total', 'Tax Amount', 'Tax Percentage',
        'Amount Paid', 'Amount Change'
    ]
    worksheet.append(columns)

    # Fetch sales data
    sales = Sale.objects.all()

    for sale in sales:
        # Convert timezone-aware datetime to naive datetime
        if sale.date_added.tzinfo is not None:
            date_added = sale.date_added.replace(tzinfo=None)
        else:
            date_added = sale.date_added

        worksheet.append([
            sale.id,
            date_added,
            sale.customer.phone,
            sale.sub_total,
            sale.grand_total,
            sale.tax_amount,
            sale.tax_percentage,
            sale.amount_paid,
            sale.amount_change
        ])

    # Set up the response to send the file
    response = HttpResponse(
        content_type=(
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    )
    response['Content-Disposition'] = 'attachment; filename=sales.xlsx'
    workbook.save(response)

    return response


def export_purchases_to_excel(request):
    # Create a workbook and select the active worksheet.
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = 'Purchases'

    # Define the column headers
    columns = [
        'ID', 'Item', 'Description', 'Vendor', 'Order Date',
        'Receipt Date', 'Quantity', 'Receipt Status',
        'Price per item (Rs)', 'Sub Total', 'Discount',
        'VAT %', 'VAT Amount', 'Net Amount', 'Amount Paid', 'Amount Remaining'
    ]
    worksheet.append(columns)

    # Fetch purchases data
    purchases = Purchase.objects.all()

    for purchase in purchases.prefetch_related("lines__item"):
        names = []
        qty_sum = 0
        lines = purchase.lines.all()
        if lines:
            for line in lines:
                names.append(line.item.name)
                qty_sum += line.quantity
        elif purchase.item_id:
            names.append(purchase.item.name)
            qty_sum = purchase.quantity
        summary = "; ".join(names)
        # Convert timezone-aware datetime to naive datetime, handling null receipt date.
        receipt_date = purchase.receipt_date
        order_date = purchase.order_date
        if receipt_date is not None and receipt_date.tzinfo is not None:
            receipt_date = receipt_date.replace(tzinfo=None)
        if order_date is not None and order_date.tzinfo is not None:
            order_date = order_date.replace(tzinfo=None)
        worksheet.append([
            purchase.id,
            summary,
            purchase.description,
            purchase.vendor.name,
            order_date,
            receipt_date,
            qty_sum,
            purchase.get_receipt_status_display(),
            (purchase.lines.first().unit_price if purchase.lines.exists() else purchase.price),
            purchase.sub_total,
            purchase.discount_amount,
            purchase.vat_percentage,
            purchase.vat_amount,
            purchase.net_amount,
            purchase.amount_paid,
            purchase.amount_remaining
        ])

    # Set up the response to send the file
    response = HttpResponse(
        content_type=(
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    )
    response['Content-Disposition'] = 'attachment; filename=purchases.xlsx'
    workbook.save(response)

    return response


class SaleListView(LoginRequiredMixin, ListView):
    """
    View to list all sales with pagination and filtering.
    """

    model = Sale
    template_name = "transactions/sales_list.html"
    context_object_name = "sales"
    paginate_by = 10
    filterset_class = SaleFilter

    def get_queryset(self):
        queryset = super().get_queryset().select_related('customer').order_by('-date_added')
        self.filterset = self.filterset_class(self.request.GET, queryset=queryset)
        return self.filterset.qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter'] = self.filterset
        return context


class SaleDetailView(LoginRequiredMixin, DetailView):
    """
    View to display details of a specific sale.
    """

    model = Sale
    template_name = "transactions/saledetail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        sale_details = self.object.saledetail_set.select_related('item').prefetch_related('item__variations')
        context['sale_details'] = sale_details
        
        # Calculate profit for this sale
        total_profit = 0
        total_cost = 0
        for detail in sale_details:
            item_cost = detail.item.cost_price if detail.item.cost_price > 0 else 0
            detail_profit = (detail.price - item_cost) * detail.quantity
            total_profit += detail_profit
            total_cost += item_cost * detail.quantity
        
        context['company'] = Company.load()
        context['total_profit'] = total_profit
        context['total_cost'] = total_cost
        context['profit_margin'] = (total_profit / self.object.grand_total * 100) if self.object.grand_total > 0 else 0
        return context


def SaleCreateView(request):
    context = {
        "active_icon": "sales",
        "customers": [c.to_select2() for c in Customer.objects.all()]
    }

    if request.method == 'POST':
        if is_ajax(request=request):
            try:
                # Load the JSON data from the request body
                data = json.loads(request.body)
                logger.info(f"Received data: {data}")

                # Validate required fields
                required_fields = [
                    'customer', 'sub_total', 'grand_total',
                    'amount_paid', 'amount_change', 'items'
                ]
                for field in required_fields:
                    if field not in data:
                        raise ValueError(f"Missing required field: {field}")

                # Create sale attributes
                sale_attributes = {
                    "customer": Customer.objects.get(id=int(data['customer'])),
                    "sub_total": float(data["sub_total"]),
                    "grand_total": float(data["grand_total"]),
                    "tax_amount": float(data.get("tax_amount", 0.0)),
                    "tax_percentage": float(data.get("tax_percentage", 0.0)),
                    "amount_paid": float(data["amount_paid"]),
                    "amount_change": float(data["amount_change"]),
                }

                # Use a transaction to ensure atomicity
                with transaction.atomic():
                    # Create the sale
                    new_sale = Sale.objects.create(**sale_attributes)
                    logger.info(f"Sale created: {new_sale}")

                    # Create sale details and update item quantities
                    items = data["items"]
                    if not isinstance(items, list):
                        raise ValueError("Items should be a list")

                    for item in items:
                        if not all(
                            k in item for k in [
                                "id", "price", "quantity", "total_item"
                            ]
                        ):
                            raise ValueError("Item is missing required fields")

                        item_instance = Item.objects.get(id=int(item["id"]))

                        detail_attributes = {
                            "sale": new_sale,
                            "item": item_instance,
                            "price": float(item["price"]),
                            "quantity": int(item["quantity"]),
                            "total_detail": float(item["total_item"])
                        }
                        SaleDetail.objects.create(**detail_attributes)
                        logger.info(f"Sale detail created: {detail_attributes}")

                    inventory_transaction = create_sale_transaction(
                        customer=sale_attributes["customer"],
                        items=[
                            {
                                "item": int(item["id"]),
                                "quantity": item["quantity"],
                                "unit_price": item["price"],
                            }
                            for item in items
                        ],
                        notes=f"Sale #{new_sale.id}",
                    )
                    new_sale.inventory_transaction = inventory_transaction
                    new_sale.save(update_fields=["inventory_transaction"])

                    paid = Decimal(str(data["amount_paid"]))
                    if paid > 0:
                        CustomerPayment.objects.create(
                            sale=new_sale,
                            amount=paid,
                            method="cash",
                            notes="POS",
                        )

                return JsonResponse(
                    {
                        'status': 'success',
                        'message': 'Sale created successfully!',
                        'redirect': '/transactions/sales/'
                    }
                )

            except json.JSONDecodeError:
                return JsonResponse(
                    {
                        'status': 'error',
                        'message': 'Invalid JSON format in request body!'
                    }, status=400)
            except Customer.DoesNotExist:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Customer does not exist!'
                    }, status=400)
            except Item.DoesNotExist:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Item does not exist!'
                    }, status=400)
            except ValueError as ve:
                return JsonResponse({
                    'status': 'error',
                    'message': f'Value error: {str(ve)}'
                    }, status=400)
            except TypeError as te:
                return JsonResponse({
                    'status': 'error',
                    'message': f'Type error: {str(te)}'
                    }, status=400)
            except Exception as e:
                logger.error(f"Exception during sale creation: {e}")
                return JsonResponse(
                    {
                        'status': 'error',
                        'message': (
                            f'There was an error during the creation: {str(e)}'
                        )
                    }, status=500)

    return render(request, "transactions/sale_create.html", context=context)


class SaleDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    """
    View to delete a sale.
    """

    model = Sale
    template_name = "transactions/saledelete.html"

    def get_success_url(self):
        """
        Redirect to the sales list after successful deletion.
        """
        return reverse("saleslist")

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        delete_inventory_transaction_and_sync(self.object.inventory_transaction)
        return super().delete(request, *args, **kwargs)

    def test_func(self):
        """
        Allow deletion only for superusers.
        """
        return self.request.user.is_superuser


class PurchaseListView(LoginRequiredMixin, ListView):
    """
    View to list all purchases with pagination and filtering.
    """

    model = Purchase
    template_name = "transactions/purchases_list.html"
    context_object_name = "purchases"
    paginate_by = 10
    filterset_class = PurchaseFilter

    def get_queryset(self):
        queryset = (
            super()
            .get_queryset()
            .select_related("vendor")
            .prefetch_related(
                "lines__item",
                "lines__item__variations",
                "item",
                "item__variations",
            )
            .distinct()
        )
        self.filterset = self.filterset_class(self.request.GET, queryset=queryset)
        return self.filterset.qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter'] = self.filterset
        context["total_outstanding"] = sum(
            [purchase.amount_remaining for purchase in context["purchases"]]
        )
        return context


class PurchaseDetailView(LoginRequiredMixin, DetailView):
    """
    View to display details of a specific purchase.
    """

    model = Purchase
    template_name = "transactions/purchasedetail.html"

    def get_queryset(self):
        return super().get_queryset().prefetch_related("lines__item", "vendor")


class PurchaseCreateView(LoginRequiredMixin, CreateView):
    """
    View to create a new purchase.
    """

    model = Purchase
    form_class = PurchaseForm
    template_name = "transactions/purchases_form.html"

    def get_success_url(self):
        """
        Redirect to the purchases list after successful form submission.
        """
        return reverse("purchaseslist")

    def get_context_data(self, **kwargs):
        kwargs.setdefault(
            "line_formset",
            PurchaseLineFormSet(self.request.POST) if self.request.method == "POST" else PurchaseLineFormSet(),
        )
        return super().get_context_data(**kwargs)

    def post(self, request, *args, **kwargs):
        self.object = None
        form_class = self.get_form_class()
        form = form_class(request.POST)
        line_formset = PurchaseLineFormSet(request.POST)
        if form.is_valid() and line_formset.is_valid():
            with transaction.atomic():
                purchase = form.save()
                line_formset.instance = purchase
                line_formset.save()
                purchase.save()
                sync_purchase_inventory_transaction(purchase=purchase)
            if purchase.receipt_status == "S":
                messages.success(
                    request,
                    "Purchase saved and inventory posted (received).",
                )
            else:
                messages.success(
                    request,
                    "Purchase saved. Stock posts only when Receipt status is Received.",
                )
            return HttpResponseRedirect(self.get_success_url())
        return self.render_to_response(
            self.get_context_data(form=form, line_formset=line_formset)
        )


class PurchaseUpdateView(LoginRequiredMixin, UpdateView):
    """
    View to update an existing purchase.
    """

    model = Purchase
    form_class = PurchaseForm
    template_name = "transactions/purchases_form.html"

    def get_success_url(self):
        """
        Redirect to the purchases list after successful form submission.
        """
        return reverse("purchaseslist")

    def get_context_data(self, **kwargs):
        kwargs.setdefault(
            "line_formset",
            PurchaseLineFormSet(
                self.request.POST,
                instance=self.object,
            )
            if self.request.method == "POST"
            else PurchaseLineFormSet(instance=self.object),
        )
        return super().get_context_data(**kwargs)

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form_class = self.get_form_class()
        form = form_class(request.POST, instance=self.object)
        line_formset = PurchaseLineFormSet(request.POST, instance=self.object)
        if form.is_valid() and line_formset.is_valid():
            with transaction.atomic():
                purchase = form.save()
                line_formset.instance = purchase
                line_formset.save()
                purchase.save()
                sync_purchase_inventory_transaction(purchase=purchase, notes_suffix=" (updated)")
            if purchase.receipt_status == "S":
                messages.success(
                    request,
                    "Purchase updated and inventory posted (received).",
                )
            else:
                messages.success(
                    request,
                    "Purchase updated. Stock stays unposted while receipt is Pending.",
                )
            return HttpResponseRedirect(self.get_success_url())
        ctx = super().get_context_data(form=form, line_formset=line_formset)
        return self.render_to_response(ctx)


class PurchaseDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    """
    View to delete a purchase.
    """

    model = Purchase
    template_name = "transactions/purchasedelete.html"

    def get_success_url(self):
        """
        Redirect to the purchases list after successful deletion.
        """
        return reverse("purchaseslist")

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        delete_inventory_transaction_and_sync(self.object.inventory_transaction)
        return super().delete(request, *args, **kwargs)

    def test_func(self):
        """
        Allow deletion only for superusers.
        """
        return self.request.user.is_superuser


class StockLedgerView(LoginRequiredMixin, ListView):
    template_name = "transactions/stock_ledger.html"
    context_object_name = "rows"
    paginate_by = 50

    def get_queryset(self):
        item_id = self.request.GET.get("item")
        date_from = self.request.GET.get("date_from")
        date_to = self.request.GET.get("date_to")
        item = Item.objects.filter(pk=item_id).first() if item_id else None
        return get_stock_ledger_rows(item=item, date_from=date_from, date_to=date_to)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["items"] = Item.objects.order_by("name")
        context["selected_item"] = self.request.GET.get("item", "")
        context["date_from"] = self.request.GET.get("date_from", "")
        context["date_to"] = self.request.GET.get("date_to", "")
        return context


class PayablesAgingView(LoginRequiredMixin, ListView):
    template_name = "transactions/payables_aging.html"
    context_object_name = "vendors"

    def get_queryset(self):
        return get_payables_aging()
