# Standard library imports
import json
import logging
from decimal import Decimal

# Django core imports
from django.http import JsonResponse, HttpResponse, HttpResponseRedirect
from django.urls import reverse
from django.shortcuts import render
from django.db import transaction
from django.db.models import Sum
from django.contrib import messages

# Class-based views
from django.views import View
from django.views.generic import DetailView, ListView
from django.views.generic.edit import CreateView, UpdateView, DeleteView

# Authentication and permissions
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin

# Third-party packages
from openpyxl import Workbook

# Local app imports
from store.list_display import annotate_list_row_numbers
from store.models import Item
from accounts.models import Customer, Company, Vendor
from .models import CustomerPayment, Purchase, Sale, SaleDetail
from .forms import (
    PayablesQuickEntryForm,
    PurchaseForm,
    PurchaseLineFormSet,
    SaleEditForm,
    _sync_purchase_vendor_payment,
)
from .filters import SaleFilter, PurchaseFilter
from .services import (
    create_sale_transaction,
    delete_inventory_transaction_and_sync,
    get_payables_aging,
    create_payable_quick_entry,
    get_payables_aging_report,
    get_stock_ledger_rows,
    sync_purchase_inventory_transaction,
    update_vendor_payables_adjustment,
    process_purchase_return,
    process_sale_return,
)


logger = logging.getLogger(__name__)


def user_can_delete_transactions(user):
    """Admins and superusers may delete sales/purchases."""
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    profile = getattr(user, "profile", None)
    return profile is not None and getattr(profile, "role", None) == "AD"


def is_ajax(request):
    return request.META.get('HTTP_X_REQUESTED_WITH') == 'XMLHttpRequest'


@login_required
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

        customer = sale.customer
        worksheet.append([
            sale.id,
            date_added,
            customer.get_full_name() if customer else "",
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


@login_required
def export_purchases_to_excel(request):
    # Create a workbook and select the active worksheet.
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = 'Purchases'

    # Define the column headers
    columns = [
        'ID', 'Bill Number', 'Item', 'Description', 'Vendor', 'Order Date',
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
            purchase.display_bill_number,
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
        queryset = (
            super()
            .get_queryset()
            .select_related("customer")
            .prefetch_related(
                "saledetail_set__item",
                "saledetail_set__variation",
            )
            .order_by("-date_added")
        )
        self.filterset = self.filterset_class(self.request.GET, queryset=queryset)
        qs = self.filterset.qs
        if not self.request.GET.get("ordering"):
            qs = qs.order_by("-date_added", "-id")
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter'] = self.filterset
        context['can_delete_sales'] = user_can_delete_transactions(self.request.user)
        context['can_edit_sales'] = self.request.user.is_authenticated
        annotate_list_row_numbers(
            context.get("sales") or [], context.get("page_obj")
        )
        return context


class SaleDetailView(LoginRequiredMixin, DetailView):
    """
    View to display details of a specific sale.
    """

    model = Sale
    template_name = "transactions/saledetail.html"

    def get_queryset(self):
        return super().get_queryset().prefetch_related(
            "saledetail_set__item",
            "saledetail_set__variation",
            "returns__lines__sale_detail__item",
        )

    def _detail_url(self):
        return reverse("sale-detail", kwargs={"pk": self.object.pk})

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        if request.POST.get("action") != "sale_return":
            messages.error(request, "Unknown action.")
            return HttpResponseRedirect(self._detail_url())

        reason = (request.POST.get("reason") or "").strip()
        line_returns = []
        for detail in self.object.saledetail_set.all():
            raw = request.POST.get(f"return_qty_{detail.id}", "").strip()
            if not raw:
                continue
            try:
                qty = int(raw)
            except ValueError:
                messages.error(request, f"Invalid quantity for {detail.item.name}.")
                return HttpResponseRedirect(self._detail_url())
            if qty > 0:
                line_returns.append({"detail_id": detail.id, "return_qty": qty})

        if not line_returns:
            messages.warning(request, "Enter at least one return quantity.")
            return HttpResponseRedirect(self._detail_url())

        try:
            credit = process_sale_return(
                self.object,
                line_returns,
                reason=reason,
                user=request.user,
            )
            messages.success(
                request,
                f"Sale return recorded. Bill reduced by Rs {credit}.",
            )
        except ValueError as exc:
            messages.error(request, str(exc))
        except Exception as exc:
            messages.error(request, f"Could not process return: {exc}")
        return HttpResponseRedirect(self._detail_url())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        sale_details = self.object.saledetail_set.select_related(
            "item", "variation"
        )
        context['sale_details'] = sale_details
        
        # Calculate profit for this sale
        total_profit = Decimal("0")
        total_cost = Decimal("0")
        for detail in sale_details:
            item_cost = (
                Decimal(str(detail.item.cost_price))
                if detail.item.cost_price and detail.item.cost_price > 0
                else Decimal("0")
            )
            detail_profit = (detail.price - item_cost) * detail.quantity
            total_profit += detail_profit
            total_cost += item_cost * detail.quantity
        
        context['company'] = Company.load()
        context['total_profit'] = total_profit
        context['total_cost'] = total_cost
        context['profit_margin'] = (total_profit / self.object.grand_total * 100) if self.object.grand_total > 0 else 0
        context['can_edit_sales'] = self.request.user.is_authenticated
        context['can_delete_sales'] = user_can_delete_transactions(self.request.user)
        return context


class SaleUpdateView(LoginRequiredMixin, UpdateView):
    """Edit sale customer, tax, and payment (line items are read-only)."""

    model = Sale
    form_class = SaleEditForm
    template_name = "transactions/sale_form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["sale_details"] = self.object.saledetail_set.select_related("item")
        context["is_edit"] = True
        return context

    def form_valid(self, form):
        sale = form.save(commit=False)
        sub_total = Decimal("0")
        for detail in sale.saledetail_set.all():
            sub_total += detail.price * detail.quantity
        sale.sub_total = sub_total
        tax_pct = Decimal(str(form.cleaned_data.get("tax_percentage") or 0))
        tax_amount = form.cleaned_data.get("tax_amount")
        if tax_pct > 0:
            sale.tax_amount = (sub_total * (tax_pct / Decimal("100"))).quantize(
                Decimal("0.01")
            )
        elif tax_amount is not None and tax_amount != "":
            sale.tax_amount = Decimal(str(tax_amount))
        else:
            sale.tax_amount = Decimal("0")
        sale.grand_total = sale.sub_total + sale.tax_amount
        paid = Decimal(str(form.cleaned_data.get("amount_paid") or 0))
        sale.amount_paid = paid
        sale.amount_change = paid - sale.grand_total
        sale.save()
        method = form.cleaned_data.get("payment_method") or "cash"
        if method not in ("cash", "bank"):
            method = "cash"
        payment = sale.customer_payments.order_by("id").first()
        if payment:
            payment.amount = paid
            payment.method = method
            payment.save()
        elif paid > 0:
            CustomerPayment.objects.create(
                sale=sale,
                amount=paid,
                method=method,
                notes="Updated from sale edit",
            )
        messages.success(self.request, "Sale updated successfully.")
        return HttpResponseRedirect(self.get_success_url())

    def get_success_url(self):
        return reverse("sale-detail", kwargs={"pk": self.object.pk})


@login_required
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

                sub_total = Decimal(str(data["sub_total"]))
                tax_pct = Decimal(str(data.get("tax_percentage", 0)))
                tax_amount = Decimal(str(data.get("tax_amount", 0)))
                if tax_amount == 0 and tax_pct:
                    tax_amount = sub_total * (tax_pct / Decimal("100"))
                grand_total = sub_total + tax_amount
                amount_paid = Decimal(str(data["amount_paid"]))
                amount_change = amount_paid - grand_total

                sale_attributes = {
                    "customer": Customer.objects.get(id=int(data['customer'])),
                    "sub_total": sub_total,
                    "grand_total": grand_total,
                    "tax_amount": tax_amount,
                    "tax_percentage": float(tax_pct),
                    "amount_paid": amount_paid,
                    "amount_change": amount_change,
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
                        variation_id = item.get("selected_variant") or None
                        variation = None
                        if variation_id:
                            from store.models import ProductVariation
                            variation = ProductVariation.objects.filter(
                                pk=int(variation_id), item=item_instance
                            ).first()

                        detail_attributes = {
                            "sale": new_sale,
                            "item": item_instance,
                            "variation": variation,
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
                                "variation_id": item.get("selected_variant") or None,
                            }
                            for item in items
                        ],
                        notes=f"Sale #{new_sale.id}",
                    )
                    new_sale.inventory_transaction = inventory_transaction
                    new_sale.save(update_fields=["inventory_transaction"])
                    inventory_transaction.source_ref = f"sale:{new_sale.id}"
                    inventory_transaction.save(update_fields=["source_ref"])

                    paid = Decimal(str(data["amount_paid"]))
                    if paid > 0:
                        method = data.get("payment_method") or "cash"
                        if method not in ("cash", "bank"):
                            method = "cash"
                        CustomerPayment.objects.create(
                            sale=new_sale,
                            amount=paid,
                            method=method,
                            notes="POS",
                        )

                return JsonResponse(
                    {
                        'status': 'success',
                        'message': 'Sale created successfully!',
                        'redirect': reverse('saleslist'),
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
        from transactions.services import sync_item_quantity_cache

        self.object = self.get_object()
        affected_items = []
        for detail in self.object.saledetail_set.select_related("variation", "item"):
            if detail.variation_id:
                variation = detail.variation
                variation.quantity = int(variation.quantity or 0) + int(detail.quantity)
                variation.save(update_fields=["quantity"])
                affected_items.append(detail.item)
        delete_inventory_transaction_and_sync(self.object.inventory_transaction)
        for payment in self.object.customer_payments.all():
            delete_inventory_transaction_and_sync(payment.inventory_transaction)
        if affected_items:
            sync_item_quantity_cache(affected_items)
        return super().delete(request, *args, **kwargs)

    def test_func(self):
        return user_can_delete_transactions(self.request.user)


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
        qs = self.filterset.qs
        if not self.request.GET.get("ordering"):
            qs = qs.order_by("-order_date", "-id")
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter'] = self.filterset
        outstanding = self.filterset.qs.aggregate(
            total=Sum("amount_remaining")
        )["total"]
        context["total_outstanding"] = outstanding or Decimal("0")
        vendor_adj = Vendor.objects.aggregate(total=Sum("payables_adjustment"))[
            "total"
        ]
        context["vendor_payables_adjustment"] = vendor_adj or Decimal("0")
        context["total_outstanding_adjusted"] = (
            context["total_outstanding"] + context["vendor_payables_adjustment"]
        )
        context["can_delete_purchases"] = user_can_delete_transactions(
            self.request.user
        )
        annotate_list_row_numbers(
            context.get("purchases") or [], context.get("page_obj")
        )
        return context


class PurchaseDetailView(LoginRequiredMixin, DetailView):
    """
    View to display details of a specific purchase.
    """

    model = Purchase
    template_name = "transactions/purchasedetail.html"
    slug_url_kwarg = "slug"
    slug_field = "slug"

    def get_queryset(self):
        return super().get_queryset().prefetch_related("lines__item", "vendor")

    def _detail_url(self):
        return reverse("purchase-detail", kwargs={"slug": self.object.slug})

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        if request.POST.get("action") != "purchase_return":
            messages.error(request, "Unknown action.")
            return HttpResponseRedirect(self._detail_url())

        reason = (request.POST.get("reason") or "").strip()
        line_returns = []
        for line in self.object.lines.all():
            raw = request.POST.get(f"return_qty_{line.id}", "").strip()
            if not raw:
                continue
            try:
                qty = int(raw)
            except ValueError:
                messages.error(request, f"Invalid quantity for {line.item.name}.")
                return HttpResponseRedirect(self._detail_url())
            if qty > 0:
                line_returns.append({"line_id": line.id, "return_qty": qty})

        if not line_returns:
            messages.warning(request, "Enter at least one return quantity.")
            return HttpResponseRedirect(self._detail_url())

        try:
            credit = process_purchase_return(
                self.object,
                line_returns,
                reason=reason,
                user=request.user,
            )
            messages.success(
                request,
                f"Return recorded. Vendor payables credited Rs {credit}.",
            )
        except ValueError as exc:
            messages.error(request, str(exc))
        except Exception as exc:
            messages.error(request, f"Could not process return: {exc}")
        return HttpResponseRedirect(self._detail_url())


def _purchase_vendor_id(request, purchase=None):
    if request.method == "POST":
        raw = request.POST.get("vendor")
        return int(raw) if raw else None
    if purchase is not None:
        return purchase.vendor_id
    return None


def _purchase_form_context(request, purchase=None, form=None, line_formset=None):
    vendor_id = _purchase_vendor_id(request, purchase)
    if line_formset is None:
        if request.method == "POST":
            line_formset = PurchaseLineFormSet(request.POST, instance=purchase, vendor_id=vendor_id)
        else:
            line_formset = PurchaseLineFormSet(instance=purchase, vendor_id=vendor_id)
    items = Item.objects.select_related("vendor").order_by("name")
    return {
        "line_formset": line_formset,
        "items_catalog": [
            {
                "id": i.id,
                "vendor_id": i.vendor_id,
                "name": i.name,
                "stock": i.quantity,
                "cost": float(i.cost_price or 0),
            }
            for i in items
        ],
    }


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
        ctx = super().get_context_data(**kwargs)
        ctx.update(_purchase_form_context(self.request, purchase=None, form=ctx.get("form")))
        return ctx

    def post(self, request, *args, **kwargs):
        self.object = None
        form_class = self.get_form_class()
        form = form_class(request.POST)
        vendor_id = _purchase_vendor_id(request)
        line_formset = PurchaseLineFormSet(request.POST, vendor_id=vendor_id)
        if form.is_valid() and line_formset.is_valid():
            with transaction.atomic():
                purchase = form.save()
                line_formset.instance = purchase
                line_formset.save()
                purchase.save()
                paid = form.cleaned_data.get("amount_paid")
                if form.fields["amount_paid"].disabled:
                    paid = purchase.amount_paid
                _sync_purchase_vendor_payment(
                    purchase,
                    paid,
                    form.cleaned_data.get("payment_method"),
                )
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
        ctx = super().get_context_data(**kwargs)
        ctx.update(_purchase_form_context(self.request, purchase=self.object, form=ctx.get("form")))
        return ctx

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form_class = self.get_form_class()
        form = form_class(request.POST, instance=self.object)
        vendor_id = _purchase_vendor_id(request, self.object)
        line_formset = PurchaseLineFormSet(
            request.POST, instance=self.object, vendor_id=vendor_id
        )
        if form.is_valid() and line_formset.is_valid():
            with transaction.atomic():
                purchase = form.save()
                line_formset.instance = purchase
                line_formset.save()
                purchase.save()
                paid = form.cleaned_data.get("amount_paid")
                if form.fields["amount_paid"].disabled:
                    paid = purchase.amount_paid
                    payment = purchase.vendor_payments.order_by("id").first()
                    if payment and form.cleaned_data.get("payment_method"):
                        payment.method = form.cleaned_data["payment_method"]
                        payment.save()
                else:
                    _sync_purchase_vendor_payment(
                        purchase,
                        paid,
                        form.cleaned_data.get("payment_method"),
                    )
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
        return user_can_delete_transactions(self.request.user)


class StockLedgerView(LoginRequiredMixin, ListView):
    template_name = "transactions/stock_ledger.html"
    context_object_name = "rows"
    paginate_by = 50

    def get_queryset(self):
        item_id = self.request.GET.get("item")
        date_from = self.request.GET.get("date_from")
        date_to = self.request.GET.get("date_to")
        item = None
        if item_id:
            try:
                item = Item.objects.filter(pk=int(item_id)).first()
            except (ValueError, TypeError):
                item = None
        return get_stock_ledger_rows(item=item, date_from=date_from, date_to=date_to)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["items"] = Item.objects.order_by("name")
        context["selected_item"] = self.request.GET.get("item", "")
        context["date_from"] = self.request.GET.get("date_from", "")
        context["date_to"] = self.request.GET.get("date_to", "")
        return context


class PayablesAgingView(LoginRequiredMixin, View):
    template_name = "transactions/payables_aging.html"
    http_method_names = ["get", "post", "head", "options"]

    def _build_totals(self, vendor_groups):
        totals = {
            "stock_units": 0,
            "stock_value": Decimal("0"),
            "outstanding": Decimal("0"),
            "adjustment": Decimal("0"),
            "balance_due": Decimal("0"),
        }
        seen_vendors = set()
        for group in vendor_groups:
            vendor_id = group["vendor"].id
            if vendor_id not in seen_vendors:
                seen_vendors.add(vendor_id)
                totals["stock_units"] += int(group["total_stock"] or 0)
                totals["stock_value"] += Decimal(str(group["total_stock_value"] or 0))
                totals["adjustment"] += Decimal(str(group["payables_adjustment"] or 0))
            totals["outstanding"] += Decimal(str(group["total_outstanding"] or 0))
            totals["balance_due"] += Decimal(str(group["balance_due"] or 0))
        return totals

    def _render_page(self, request, vendor_groups=None, quick_form=None):
        if vendor_groups is None:
            vendor_groups = get_payables_aging_report()
        if quick_form is None:
            quick_form = PayablesQuickEntryForm()
        return render(
            request,
            self.template_name,
            {
                "vendor_groups": vendor_groups,
                "totals": self._build_totals(vendor_groups),
                "quick_entry_form": quick_form,
            },
        )

    def get(self, request, *args, **kwargs):
        return self._render_page(request)

    def post(self, request, *args, **kwargs):
        action = request.POST.get("action", "adjustment")
        if action == "add_record":
            return self._post_add_record(request)
        return self._post_adjustment(request)

    def _post_add_record(self, request):
        form = PayablesQuickEntryForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Could not add payable. Please check the form.")
            return self._render_page(request, quick_form=form)
        try:
            purchase = create_payable_quick_entry(
                form.cleaned_data["vendor"],
                bill_number=form.cleaned_data.get("bill_number") or "",
                order_date=form.cleaned_data.get("order_date"),
                net_amount=form.cleaned_data["net_amount"],
                amount_paid=form.cleaned_data.get("amount_paid") or 0,
                description=form.cleaned_data.get("description") or "",
            )
            messages.success(
                request,
                f"Payable recorded: {purchase.display_bill_number} "
                f"(Rs {purchase.amount_remaining} outstanding).",
            )
        except Exception as exc:
            messages.error(request, f"Could not add payable: {exc}")
            return self._render_page(request, quick_form=form)
        return HttpResponseRedirect(reverse("payables-aging"))

    def _post_adjustment(self, request):
        vendor_id = request.POST.get("vendor_id")
        adjustment_amount = request.POST.get("adjustment_amount", "0")
        adjustment_sign = request.POST.get("adjustment_sign", "+")
        if adjustment_sign not in ("+", "-"):
            adjustment_sign = "+"
        if not vendor_id:
            messages.error(request, "Vendor is required.")
            return HttpResponseRedirect(reverse("payables-aging"))
        try:
            update_vendor_payables_adjustment(
                vendor_id, adjustment_amount, sign=adjustment_sign
            )
            messages.success(request, "Payables adjustment saved.")
        except Vendor.DoesNotExist:
            messages.error(request, "Vendor not found.")
        except Exception as exc:
            messages.error(request, f"Could not save adjustment: {exc}")
        return HttpResponseRedirect(reverse("payables-aging"))
