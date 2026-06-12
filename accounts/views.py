# Django core imports
from decimal import Decimal

from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.urls import reverse_lazy, reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.db.models import Q

# Authentication and permissions
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin

# Class-based views
from django.views.generic import (
    DetailView,
    ListView,
    CreateView,
    UpdateView,
    DeleteView,
    View,
)

# Third-party packages
from django_tables2 import SingleTableView
from django_tables2.export.views import ExportMixin

# Local app imports
from .models import Profile, Customer, Vendor, Logistics
from .contact_ledger import (
    get_customer_balance_due,
    get_customer_ledger_rows,
    get_vendor_balance_due,
    get_vendor_ledger_rows,
    should_show_opening_balance,
    update_customer_receivables_adjustment,
)
from .forms import (
    CreateUserForm, UserUpdateForm,
    ProfileUpdateForm, CustomerForm,
    VendorForm, VendorBrandForm, LogisticsForm,
    SignedOpeningBalanceForm,
    CustomerPaymentForm,
    VendorPaymentForm,
    SignedAdjustmentForm,
    PaymentEditForm,
    CustomerAccountTransactionForm,
    VendorAccountTransactionForm,
    _signed_opening_initial,
)
from .tables import ProfileTable
from store.list_display import NormalizePageMixin, annotate_list_row_numbers
from .account_dates import (
    apply_payment_date,
    save_all_ledger_dates,
    update_account_transaction_date,
)
from .ledger_actions import delete_ledger_row, update_ledger_row_amount
from .datetime_utils import parse_posted_datetime, resolve_posted_transaction_date
from .vendor_brands import handle_vendor_brand_action
from store.query_redirect import redirect_preserving_query


def _redirect_customer_detail(request, customer):
    return redirect_preserving_query(
        request, reverse("customer-detail", kwargs={"pk": customer.pk})
    )


def _redirect_vendor_detail(request, vendor):
    return redirect_preserving_query(
        request, reverse("vendor-detail", kwargs={"pk": vendor.pk})
    )


def register(request):
    """
    Handle user registration.
    If the request is POST, process the form data to create a new user.
    Redirect to the login page on successful registration.
    For GET requests, render the registration form.
    """
    if request.method == 'POST':
        form = CreateUserForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('user-login')
    else:
        form = CreateUserForm()

    return render(request, 'accounts/register.html', {'form': form})


@login_required
def profile(request):
    """
    Render the user profile page.
    Requires user to be logged in.
    """
    return render(request, 'accounts/profile.html')


@login_required
def profile_update(request):
    """
    Handle profile update.
    If the request is POST, process the form data
    to update user information and profile.
    Redirect to the profile page on success.
    For GET requests, render the update forms.
    """
    if request.method == 'POST':
        u_form = UserUpdateForm(request.POST, instance=request.user)
        p_form = ProfileUpdateForm(
            request.POST,
            request.FILES,
            instance=request.user.profile
        )
        if u_form.is_valid() and p_form.is_valid():
            u_form.save()
            p_form.save()
            return redirect('user-profile')
    else:
        u_form = UserUpdateForm(instance=request.user)
        p_form = ProfileUpdateForm(instance=request.user.profile)

    return render(
        request,
        'accounts/profile_update.html',
        {'u_form': u_form, 'p_form': p_form}
    )


class ProfileListView(LoginRequiredMixin, ExportMixin, SingleTableView):
    """
    Display a list of profiles in a table format.
    Requires user to be logged in
    and supports exporting the table data.
    Pagination is applied with 10 profiles per page.
    """
    model = Profile
    template_name = 'accounts/stafflist.html'
    context_object_name = 'profiles'
    table_class = ProfileTable
    paginate_by = 10
    table_pagination = False


class ProfileCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    """
    Create a new profile.
    Requires user to be logged in and have superuser status.
    Redirects to the profile list upon successful creation.
    """
    model = Profile
    template_name = 'accounts/staffcreate.html'
    fields = ['user', 'role', 'status']

    def get_success_url(self):
        """
        Return the URL to redirect to after successfully creating a profile.
        """
        return reverse('profile_list')

    def test_func(self):
        """
        Check if the user is a superuser.
        """
        return self.request.user.is_superuser


class ProfileUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    """
    Update an existing profile.
    Requires user to be logged in and have superuser status.
    Redirects to the profile list upon successful update.
    """
    model = Profile
    template_name = 'accounts/staffupdate.html'
    fields = ['user', 'role', 'status']

    def get_success_url(self):
        """
        Return the URL to redirect to after successfully updating a profile.
        """
        return reverse('profile_list')

    def test_func(self):
        """
        Check if the user is a superuser.
        """
        return self.request.user.is_superuser


class ProfileDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    """
    Delete an existing profile.
    Requires user to be logged in and have superuser status.
    Redirects to the profile list upon successful deletion.
    """
    model = Profile
    template_name = 'accounts/staffdelete.html'

    def get_success_url(self):
        """
        Return the URL to redirect to after successfully deleting a profile.
        """
        return reverse('profile_list')

    def test_func(self):
        """
        Check if the user is a superuser.
        """
        return self.request.user.is_superuser


class CustomerListView(LoginRequiredMixin, ListView):
    """
    View for listing all customers.

    Requires the user to be logged in. Displays a list of all Customer objects.
    """
    model = Customer
    template_name = 'accounts/customer_list.html'
    context_object_name = 'customers'


class AccountsBookView(LoginRequiredMixin, View):
    """Customer and supplier account balances with links to transaction pages."""

    template_name = "accounts/accounts_book.html"

    def get(self, request):
        from django.shortcuts import render

        tab = request.GET.get("tab", "customers")
        if tab not in ("customers", "suppliers"):
            tab = "customers"
        customer_rows = [
            {
                "customer": customer,
                "balance_due": get_customer_balance_due(customer),
                "show_opening_balance": should_show_opening_balance(
                    customer.opening_balance,
                    customer.receivables_adjustment,
                ),
            }
            for customer in Customer.objects.order_by("first_name", "last_name", "id")
        ]
        supplier_rows = [
            {
                "vendor": vendor,
                "balance_due": get_vendor_balance_due(vendor),
                "show_opening_balance": should_show_opening_balance(
                    vendor.opening_balance,
                    vendor.payables_adjustment,
                ),
            }
            for vendor in Vendor.objects.order_by("name")
        ]
        return render(
            request,
            self.template_name,
            {
                "active_tab": tab,
                "customer_rows": customer_rows,
                "supplier_rows": supplier_rows,
            },
        )


def _customer_opening_form(customer):
    form = SignedOpeningBalanceForm(
        initial=_signed_opening_initial(customer.opening_balance),
        opening_balance_date=customer.opening_balance_date,
    )
    form.fields["opening_sign"].choices = [
        ("+", "Receivable (+)"),
        ("-", "Payable (−)"),
    ]
    return form


def _vendor_opening_form(vendor):
    form = SignedOpeningBalanceForm(
        initial=_signed_opening_initial(vendor.opening_balance),
        opening_balance_date=vendor.opening_balance_date,
    )
    form.fields["opening_sign"].choices = [
        ("+", "Payable (+)"),
        ("-", "Receivable (−)"),
    ]
    return form


def _customer_detail_context(customer):
    from transactions.models import CustomerPayment

    ledger_rows, balance_due = get_customer_ledger_rows(customer)
    return {
        "customer": customer,
        "party_type": "customer",
        "ledger_rows": ledger_rows,
        "balance_due": balance_due,
        "opening_form": _customer_opening_form(customer),
        "account_txn_form": CustomerAccountTransactionForm(),
        "payment_form": CustomerPaymentForm(customer=customer),
        "receivables_form": SignedAdjustmentForm(
            initial={
                "adjustment_sign": "+" if customer.receivables_adjustment >= 0 else "-",
                "adjustment_amount": abs(customer.receivables_adjustment),
            }
        ),
        "payment_records": CustomerPayment.objects.filter(
            sale__customer=customer
        ).select_related("sale").order_by("-received_at", "-id"),
    }


def _vendor_detail_context(vendor):
    from transactions.models import VendorPayment

    ledger_rows, balance_due = get_vendor_ledger_rows(vendor)
    return {
        "vendor": vendor,
        "party_type": "vendor",
        "ledger_rows": ledger_rows,
        "balance_due": balance_due,
        "opening_form": _vendor_opening_form(vendor),
        "account_txn_form": VendorAccountTransactionForm(),
        "payables_form": SignedAdjustmentForm(
            initial={
                "adjustment_sign": "+" if vendor.payables_adjustment >= 0 else "-",
                "adjustment_amount": abs(vendor.payables_adjustment),
            }
        ),
        "payment_form": VendorPaymentForm(vendor=vendor),
        "payment_records": VendorPayment.objects.filter(
            purchase__vendor=vendor
        ).select_related("purchase").order_by("-paid_at", "-id"),
        "brands": vendor.brands.order_by("name"),
        "brand_form": VendorBrandForm(),
    }


class CustomerCreateView(LoginRequiredMixin, CreateView):
    """
    View for creating a new customer.

    Requires the user to be logged in.
    Provides a form for creating a new Customer object.
    On successful form submission, redirects to the customer list.
    """
    model = Customer
    template_name = 'accounts/customer_form.html'
    form_class = CustomerForm
    success_url = reverse_lazy('customer_list')


class CustomerUpdateView(LoginRequiredMixin, UpdateView):
    """
    View for updating an existing customer.

    Requires the user to be logged in.
    Provides a form for editing an existing Customer object.
    On successful form submission, redirects to the customer list.
    """
    model = Customer
    template_name = 'accounts/customer_form.html'
    form_class = CustomerForm
    success_url = reverse_lazy('customer_list')


class CustomerDetailView(LoginRequiredMixin, View):
    template_name = "accounts/customer_detail.html"

    def get(self, request, pk):
        from django.shortcuts import get_object_or_404, render

        customer = get_object_or_404(Customer, pk=pk)
        return render(request, self.template_name, _customer_detail_context(customer))

    def post(self, request, pk):
        from django.contrib import messages
        from django.shortcuts import get_object_or_404, redirect, render
        from transactions.models import CustomerPayment

        customer = get_object_or_404(Customer, pk=pk)
        action = request.POST.get("action")

        if action == "opening_balance":
            form = SignedOpeningBalanceForm(request.POST)
            if form.is_valid():
                customer.opening_balance = form.opening_balance_value()
                customer.opening_balance_date = form.cleaned_data.get(
                    "opening_balance_date"
                )
                customer.save(
                    update_fields=["opening_balance", "opening_balance_date"]
                )
                messages.success(request, "Opening balance updated.")
                return _redirect_customer_detail(request, customer)
        elif action == "account_transaction":
            from transactions.services import (
                allocate_customer_credit_to_sales,
                create_receivable_quick_entry,
            )

            form = CustomerAccountTransactionForm(request.POST)
            if form.is_valid():
                txn_type = form.cleaned_data["transaction_type"]
                amount = form.cleaned_data["amount"]
                method = form.cleaned_data["method"]
                notes = form.cleaned_data.get("notes") or ""
                reference = form.cleaned_data.get("reference") or ""
                try:
                    txn_date = resolve_posted_transaction_date(request, form)
                    if not txn_date:
                        messages.error(request, "Enter a valid transaction date.")
                    elif txn_type == "sale_in":
                        create_receivable_quick_entry(
                            customer,
                            reference=reference,
                            amount=amount,
                            description=notes or "Account book sale in",
                            payment_method=method,
                            sale_date=txn_date,
                        )
                        messages.success(request, "Sale in recorded.")
                    else:
                        applied = allocate_customer_credit_to_sales(
                            customer, amount, payment_date=txn_date
                        )
                        remainder = amount - applied
                        if remainder > 0:
                            create_receivable_quick_entry(
                                customer,
                                reference=reference,
                                amount=remainder,
                                amount_received=remainder,
                                description=notes or "Account book payment in",
                                payment_method=method,
                                sale_date=txn_date,
                                payment_date=txn_date,
                                receipt_only=True,
                            )
                        if applied == 0 and remainder > 0:
                            messages.success(
                                request,
                                "Payment in recorded (new paid sale entry).",
                            )
                        elif applied > 0 and remainder > 0:
                            messages.success(
                                request,
                                f"Rs {applied} applied to unpaid sales; "
                                f"Rs {remainder} recorded as a new paid sale.",
                            )
                        else:
                            messages.success(request, "Payment in recorded.")
                    if txn_date:
                        return _redirect_customer_detail(request, customer)
                except Exception as exc:
                    messages.error(request, f"Could not save transaction: {exc}")
            else:
                messages.error(
                    request,
                    "Enter valid transaction details. "
                    + " ".join(e for errs in form.errors.values() for e in errs),
                )
        elif action == "save_all_transaction_dates":
            ok, msg = save_all_ledger_dates("customer", customer, request.POST)
            if ok:
                messages.success(request, msg)
            else:
                messages.error(request, msg)
            return _redirect_customer_detail(request, customer)
        elif action == "update_ledger_amount":
            ok, msg = update_ledger_row_amount(
                "customer",
                customer,
                request.POST.get("row_kind"),
                request.POST.get("row_id"),
                request.POST.get("amount"),
                request.POST.get("amount_side"),
            )
            if ok:
                messages.success(request, msg)
            else:
                messages.error(request, msg)
            return _redirect_customer_detail(request, customer)
        elif action == "delete_ledger_row":
            ok, msg = delete_ledger_row(
                "customer",
                customer,
                request.POST.get("row_kind"),
                request.POST.get("row_id"),
            )
            if ok:
                messages.success(request, msg)
            else:
                messages.error(request, msg)
            return _redirect_customer_detail(request, customer)
        elif action == "record_payment":
            form = CustomerPaymentForm(request.POST, customer=customer)
            if form.is_valid():
                sale = form.cleaned_data["sale"]
                payment = CustomerPayment.objects.create(
                    sale=sale,
                    amount=form.cleaned_data["amount"],
                    method=form.cleaned_data["method"],
                    notes=form.cleaned_data.get("notes") or "Recorded from customer account",
                )
                txn_date = form.cleaned_data.get("transaction_date")
                if txn_date:
                    apply_payment_date(
                        payment,
                        "customer",
                        txn_date.strftime("%Y-%m-%dT%H:%M"),
                    )
                sale.save()
                messages.success(request, "Payment recorded.")
                return _redirect_customer_detail(request, customer)
            messages.error(
                request,
                "Could not record payment. "
                + " ".join(e for errs in form.errors.values() for e in errs),
            )
        elif action == "receivables_adjustment":
            form = SignedAdjustmentForm(request.POST)
            if form.is_valid():
                try:
                    update_customer_receivables_adjustment(
                        customer.pk,
                        form.cleaned_data["adjustment_amount"],
                        sign=form.cleaned_data["adjustment_sign"],
                    )
                    messages.success(request, "Balance adjustment saved.")
                    return _redirect_customer_detail(request, customer)
                except Exception as exc:
                    messages.error(request, f"Could not save adjustment: {exc}")
            else:
                messages.error(
                    request,
                    "Enter a valid adjustment amount (0 or greater).",
                )
        elif action == "update_payment":
            form = PaymentEditForm(request.POST)
            payment = CustomerPayment.objects.filter(
                pk=request.POST.get("payment_id"),
                sale__customer=customer,
            ).select_related("sale").first()
            if payment and form.is_valid():
                payment.amount = form.cleaned_data["amount"]
                payment.method = form.cleaned_data["method"]
                payment.notes = form.cleaned_data.get("notes") or ""
                payment.save()
                apply_payment_date(
                    payment,
                    "customer",
                    request.POST.get("transaction_date"),
                )
                payment.sale.save()
                messages.success(request, "Payment updated.")
                return _redirect_customer_detail(request, customer)
            messages.error(request, "Could not update payment.")
            return _redirect_customer_detail(request, customer)
        elif action == "update_transaction_date":
            ok, msg = update_account_transaction_date(
                "customer",
                customer,
                request.POST.get("date_kind"),
                request.POST.get("object_id"),
                request.POST.get("transaction_date"),
            )
            if ok:
                messages.success(request, msg)
            else:
                messages.error(request, msg)
            return _redirect_customer_detail(request, customer)
        elif action == "delete_payment":
            payment = CustomerPayment.objects.filter(
                pk=request.POST.get("payment_id"),
                sale__customer=customer,
            ).select_related("sale").first()
            if payment:
                sale = payment.sale
                payment.delete()
                sale.save()
                messages.success(request, "Payment deleted.")
            else:
                messages.error(request, "Payment not found.")
            return _redirect_customer_detail(request, customer)
        else:
            messages.error(request, "Unknown action.")
            return _redirect_customer_detail(request, customer)

        ctx = _customer_detail_context(customer)
        if action == "opening_balance":
            ctx["opening_form"] = form
        elif action == "receivables_adjustment":
            ctx["receivables_form"] = form
        elif action == "account_transaction":
            ctx["account_txn_form"] = form
        elif action == "record_payment":
            ctx["payment_form"] = form
        return render(request, self.template_name, ctx)


class CustomerStatementView(LoginRequiredMixin, View):
    template_name = "accounts/account_statement.html"

    def get(self, request, pk):
        from django.shortcuts import get_object_or_404
        from django.utils import timezone

        customer = get_object_or_404(Customer, pk=pk)
        ledger_rows, balance = get_customer_ledger_rows(customer)
        return render(
            request,
            self.template_name,
            {
                "party_name": customer.get_full_name(),
                "party_label": "Customer",
                "ledger_rows": ledger_rows,
                "balance_due": balance,
                "printed_at": timezone.localtime(),
                "back_url": reverse("customer-detail", kwargs={"pk": customer.pk}),
            },
        )


class CustomerDeleteView(LoginRequiredMixin, DeleteView):
    """
    View for deleting a customer.

    Requires the user to be logged in.
    Displays a confirmation page for deleting an existing Customer object.
    On confirmation, deletes the object and redirects to the accounts book.
    """
    model = Customer
    template_name = 'accounts/customer_confirm_delete.html'
    success_url = reverse_lazy('accounts-book')

    def get_success_url(self):
        return reverse('accounts-book') + '?tab=customers'

    def delete(self, request, *args, **kwargs):
        from django.db import IntegrityError
        from django.contrib import messages
        from django.shortcuts import redirect

        self.object = self.get_object()
        try:
            return super().delete(request, *args, **kwargs)
        except IntegrityError:
            messages.error(
                request,
                "Cannot delete this customer — they are linked to sales records.",
            )
            return redirect(self.get_success_url())


def is_ajax(request):
    return request.META.get('HTTP_X_REQUESTED_WITH') == 'XMLHttpRequest'


@csrf_exempt
@require_POST
@login_required
def get_customers(request):
    if is_ajax(request) and request.method == 'POST':
        term = request.POST.get('term', '')
        customers = Customer.objects.filter(
            Q(first_name__icontains=term) | Q(last_name__icontains=term)
        )
        customer_list = [
            {"id": customer.id, "name": customer.get_full_name().strip()}
            for customer in customers
        ]
        return JsonResponse(customer_list, safe=False)
    return JsonResponse({'error': 'Invalid request method'}, status=400)


@require_POST
@login_required
def create_customer_quick(request):
    """Create a customer from the sale page without leaving the form."""
    first_name = (request.POST.get("first_name") or "").strip()
    if not first_name:
        return JsonResponse(
            {"status": "error", "message": "First name is required."},
            status=400,
        )
    last_name = (request.POST.get("last_name") or "").strip() or None
    phone = (request.POST.get("phone") or "").strip() or None
    email = (request.POST.get("email") or "").strip() or None
    customer = Customer.objects.create(
        first_name=first_name,
        last_name=last_name,
        phone=phone,
        email=email or None,
    )
    full_name = customer.get_full_name().strip()
    return JsonResponse(
        {
            "status": "success",
            "id": customer.id,
            "name": full_name,
            "label": full_name,
            "value": customer.id,
        }
    )


@login_required
def vendor_brands_json(request, pk):
    """JSON list of brands for a supplier (product form cascade)."""
    from .models import Brand

    brands = Brand.objects.filter(vendor_id=pk, is_active=True).order_by("name")
    return JsonResponse(
        [{"id": b.id, "name": b.name} for b in brands],
        safe=False,
    )


@require_POST
@login_required
def create_vendor_quick(request):
    """Create a supplier from the purchase form without leaving the page."""
    name = (request.POST.get("name") or "").strip()
    if not name:
        return JsonResponse(
            {"status": "error", "message": "Supplier name is required."},
            status=400,
        )
    phone_val = (request.POST.get("phone_number") or "").strip() or None
    vendor = Vendor.objects.create(
        name=name,
        phone_number=phone_val,
        address=(request.POST.get("address") or "").strip() or None,
    )
    return JsonResponse(
        {
            "status": "success",
            "id": vendor.id,
            "name": vendor.name,
            "label": vendor.name,
            "value": vendor.id,
        }
    )


class VendorListView(NormalizePageMixin, LoginRequiredMixin, ListView):
    model = Vendor
    template_name = 'accounts/vendor_list.html'
    context_object_name = 'vendors'
    paginate_by = 10

    def get_queryset(self):
        return Vendor.objects.prefetch_related("brands").order_by("name")

    def post(self, request, *args, **kwargs):
        from django.contrib import messages
        from django.shortcuts import get_object_or_404

        vendor_id = request.POST.get("vendor_id")
        if not vendor_id:
            messages.error(request, "Supplier not specified.")
            return redirect("vendor-list")
        vendor = get_object_or_404(Vendor, pk=vendor_id)
        if handle_vendor_brand_action(request, vendor):
            url = reverse("vendor-list")
            page = request.POST.get("page")
            if page:
                url = f"{url}?page={page}&expand={vendor.pk}"
            else:
                url = f"{url}?expand={vendor.pk}"
            return redirect(url)
        messages.error(request, "Unknown action.")
        return redirect("vendor-list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        annotate_list_row_numbers(context.get("vendors") or [], context.get("page_obj"))
        context["expand_vendor_id"] = self.request.GET.get("expand")
        return context


class VendorCreateView(LoginRequiredMixin, CreateView):
    model = Vendor
    form_class = VendorForm
    template_name = 'accounts/vendor_form.html'
    success_url = reverse_lazy('vendor-list')


class VendorUpdateView(LoginRequiredMixin, UpdateView):
    model = Vendor
    form_class = VendorForm
    template_name = 'accounts/vendor_form.html'
    success_url = reverse_lazy('vendor-list')


class VendorDetailView(LoginRequiredMixin, View):
    template_name = "accounts/vendor_detail.html"

    def get(self, request, pk):
        from django.shortcuts import get_object_or_404, render

        vendor = get_object_or_404(Vendor, pk=pk)
        return render(request, self.template_name, _vendor_detail_context(vendor))

    def post(self, request, pk):
        from django.contrib import messages
        from django.shortcuts import get_object_or_404, redirect, render
        from transactions.models import VendorPayment

        vendor = get_object_or_404(Vendor, pk=pk)
        action = request.POST.get("action")

        if action == "opening_balance":
            form = SignedOpeningBalanceForm(request.POST)
            if form.is_valid():
                vendor.opening_balance = form.opening_balance_value()
                vendor.opening_balance_date = form.cleaned_data.get(
                    "opening_balance_date"
                )
                vendor.save(
                    update_fields=["opening_balance", "opening_balance_date"]
                )
                messages.success(request, "Opening balance updated.")
                return _redirect_vendor_detail(request, vendor)
        elif action == "account_transaction":
            from transactions.services import (
                allocate_vendor_credit_to_purchases,
                create_payable_quick_entry,
            )

            form = VendorAccountTransactionForm(request.POST)
            if form.is_valid():
                txn_type = form.cleaned_data["transaction_type"]
                amount = form.cleaned_data["amount"]
                method = form.cleaned_data["method"]
                notes = form.cleaned_data.get("notes") or ""
                reference = form.cleaned_data.get("reference") or ""
                try:
                    txn_date = resolve_posted_transaction_date(request, form)
                    if not txn_date:
                        messages.error(request, "Enter a valid transaction date.")
                    elif txn_type == "bill_in":
                        paid_now = form.cleaned_data.get("amount_paid") or Decimal("0")
                        create_payable_quick_entry(
                            vendor,
                            bill_number=reference,
                            order_date=txn_date,
                            net_amount=amount,
                            amount_paid=paid_now,
                            description=notes or "Account book bill in",
                            payment_method=method,
                            payment_date=txn_date if paid_now > 0 else None,
                        )
                        messages.success(request, "Bill in recorded.")
                    else:
                        applied = allocate_vendor_credit_to_purchases(
                            vendor, amount, payment_date=txn_date
                        )
                        remainder = amount - applied
                        if remainder > 0:
                            create_payable_quick_entry(
                                vendor,
                                bill_number=reference,
                                order_date=txn_date,
                                net_amount=remainder,
                                amount_paid=remainder,
                                description=notes or "Account book payment out",
                                payment_method=method,
                                payment_date=txn_date,
                                payment_only=True,
                            )
                        if applied == 0 and remainder > 0:
                            messages.success(
                                request,
                                "Payment out recorded (new paid bill entry).",
                            )
                        elif applied > 0 and remainder > 0:
                            messages.success(
                                request,
                                f"Rs {applied} applied to outstanding bills; "
                                f"Rs {remainder} recorded as a new paid bill.",
                            )
                        else:
                            messages.success(request, "Payment out recorded.")
                    if txn_date:
                        return _redirect_vendor_detail(request, vendor)
                except Exception as exc:
                    messages.error(request, f"Could not save transaction: {exc}")
            else:
                messages.error(
                    request,
                    "Enter valid transaction details. "
                    + " ".join(e for errs in form.errors.values() for e in errs),
                )
        elif action == "save_all_transaction_dates":
            ok, msg = save_all_ledger_dates("vendor", vendor, request.POST)
            if ok:
                messages.success(request, msg)
            else:
                messages.error(request, msg)
            return _redirect_vendor_detail(request, vendor)
        elif action == "update_ledger_amount":
            ok, msg = update_ledger_row_amount(
                "vendor",
                vendor,
                request.POST.get("row_kind"),
                request.POST.get("row_id"),
                request.POST.get("amount"),
                request.POST.get("amount_side"),
            )
            if ok:
                messages.success(request, msg)
            else:
                messages.error(request, msg)
            return _redirect_vendor_detail(request, vendor)
        elif action == "delete_ledger_row":
            ok, msg = delete_ledger_row(
                "vendor",
                vendor,
                request.POST.get("row_kind"),
                request.POST.get("row_id"),
            )
            if ok:
                messages.success(request, msg)
            else:
                messages.error(request, msg)
            return _redirect_vendor_detail(request, vendor)
        elif action == "payables_adjustment":
            from transactions.services import update_vendor_payables_adjustment

            form = SignedAdjustmentForm(request.POST)
            if form.is_valid():
                try:
                    update_vendor_payables_adjustment(
                        vendor.pk,
                        form.cleaned_data["adjustment_amount"],
                        sign=form.cleaned_data["adjustment_sign"],
                    )
                    messages.success(request, "Payables adjustment saved.")
                    return _redirect_vendor_detail(request, vendor)
                except Exception as exc:
                    messages.error(request, f"Could not save adjustment: {exc}")
            else:
                messages.error(
                    request,
                    "Enter a valid adjustment amount (0 or greater).",
                )
        elif action == "record_payment":
            form = VendorPaymentForm(request.POST, vendor=vendor)
            if form.is_valid():
                purchase = form.cleaned_data["purchase"]
                payment = VendorPayment.objects.create(
                    purchase=purchase,
                    amount=form.cleaned_data["amount"],
                    method=form.cleaned_data["method"],
                    notes=form.cleaned_data.get("notes") or "Recorded from supplier account",
                )
                txn_date = form.cleaned_data.get("transaction_date")
                if txn_date:
                    apply_payment_date(
                        payment,
                        "vendor",
                        txn_date.strftime("%Y-%m-%dT%H:%M"),
                    )
                purchase.save()
                messages.success(request, "Payment recorded.")
                return _redirect_vendor_detail(request, vendor)
            messages.error(
                request,
                "Could not record payment. "
                + " ".join(e for errs in form.errors.values() for e in errs),
            )
        elif action == "update_payment":
            form = PaymentEditForm(request.POST)
            payment = VendorPayment.objects.filter(
                pk=request.POST.get("payment_id"),
                purchase__vendor=vendor,
            ).select_related("purchase").first()
            if payment and form.is_valid():
                payment.amount = form.cleaned_data["amount"]
                payment.method = form.cleaned_data["method"]
                payment.notes = form.cleaned_data.get("notes") or ""
                payment.save()
                apply_payment_date(
                    payment,
                    "vendor",
                    request.POST.get("transaction_date"),
                )
                payment.purchase.save()
                messages.success(request, "Payment updated.")
                return _redirect_vendor_detail(request, vendor)
            messages.error(request, "Could not update payment.")
            return _redirect_vendor_detail(request, vendor)
        elif action == "update_transaction_date":
            ok, msg = update_account_transaction_date(
                "vendor",
                vendor,
                request.POST.get("date_kind"),
                request.POST.get("object_id"),
                request.POST.get("transaction_date"),
            )
            if ok:
                messages.success(request, msg)
            else:
                messages.error(request, msg)
            return _redirect_vendor_detail(request, vendor)
        elif action == "delete_payment":
            payment = VendorPayment.objects.filter(
                pk=request.POST.get("payment_id"),
                purchase__vendor=vendor,
            ).select_related("purchase").first()
            if payment:
                purchase = payment.purchase
                payment.delete()
                purchase.save()
                messages.success(request, "Payment deleted.")
            else:
                messages.error(request, "Payment not found.")
            return _redirect_vendor_detail(request, vendor)
        elif action in ("add_brand", "update_brand", "delete_brand"):
            handle_vendor_brand_action(request, vendor)
            return _redirect_vendor_detail(request, vendor)
        else:
            messages.error(request, "Unknown action.")
            return _redirect_vendor_detail(request, vendor)

        ctx = _vendor_detail_context(vendor)
        if action == "opening_balance":
            ctx["opening_form"] = form
        elif action == "payables_adjustment":
            ctx["payables_form"] = form
        elif action == "add_brand":
            ctx["brand_form"] = form
        elif action == "receivables_adjustment":
            ctx["receivables_form"] = form
        elif action == "account_transaction":
            ctx["account_txn_form"] = form
        elif action == "record_payment":
            ctx["payment_form"] = form
        return render(request, self.template_name, ctx)


class VendorStatementView(LoginRequiredMixin, View):
    template_name = "accounts/account_statement.html"

    def get(self, request, pk):
        from django.shortcuts import get_object_or_404
        from django.utils import timezone

        vendor = get_object_or_404(Vendor, pk=pk)
        ledger_rows, balance = get_vendor_ledger_rows(vendor)
        return render(
            request,
            self.template_name,
            {
                "party_name": vendor.name,
                "party_label": "Supplier",
                "ledger_rows": ledger_rows,
                "balance_due": balance,
                "printed_at": timezone.localtime(),
                "back_url": reverse("vendor-detail", kwargs={"pk": vendor.pk}),
            },
        )


class VendorDeleteView(LoginRequiredMixin, DeleteView):
    model = Vendor
    template_name = 'accounts/vendor_confirm_delete.html'
    success_url = reverse_lazy('accounts-book')

    def get_success_url(self):
        return reverse('accounts-book') + '?tab=suppliers'

    def delete(self, request, *args, **kwargs):
        from django.db import IntegrityError
        from django.contrib import messages
        from django.shortcuts import redirect

        self.object = self.get_object()
        try:
            return super().delete(request, *args, **kwargs)
        except IntegrityError:
            messages.error(
                request,
                "Cannot delete this supplier — they are linked to purchase records.",
            )
            return redirect(self.get_success_url())


class LogisticsListView(LoginRequiredMixin, ListView):
    model = Logistics
    template_name = 'accounts/logistics_list.html'
    context_object_name = 'logistics'
    paginate_by = 10


class LogisticsCreateView(LoginRequiredMixin, CreateView):
    model = Logistics
    form_class = LogisticsForm
    template_name = 'accounts/logistics_form.html'
    success_url = reverse_lazy('logistics-list')


class LogisticsUpdateView(LoginRequiredMixin, UpdateView):
    model = Logistics
    form_class = LogisticsForm
    template_name = 'accounts/logistics_form.html'
    success_url = reverse_lazy('logistics-list')


class LogisticsDeleteView(LoginRequiredMixin, DeleteView):
    model = Logistics
    template_name = 'accounts/logistics_confirm_delete.html'
    success_url = reverse_lazy('logistics-list')
