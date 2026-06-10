from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from decimal import Decimal

from django.utils import timezone

from transactions.models import PAYMENT_METHOD_CHOICES, CustomerPayment, Purchase, Sale, VendorPayment

from .datetime_utils import DATETIME_LOCAL_FORMAT
from .models import Profile, Customer, Vendor, Brand, Logistics


def _d(value):
    return Decimal(str(value or 0))


def _transaction_date_field(*, label="Date", required=False):
    return forms.DateTimeField(
        required=required,
        label=label,
        widget=forms.DateTimeInput(
            attrs={"type": "datetime-local", "class": "d-none"},
            format=DATETIME_LOCAL_FORMAT,
        ),
        input_formats=[DATETIME_LOCAL_FORMAT],
    )


class CreateUserForm(UserCreationForm):
    """Form for creating a new user with an email field."""
    email = forms.EmailField()

    class Meta:
        """Meta options for the CreateUserForm."""
        model = User
        fields = [
            'username',
            'email',
            'password1',
            'password2'
        ]


class UserUpdateForm(forms.ModelForm):
    """Form for updating existing user information."""
    class Meta:
        """Meta options for the UserUpdateForm."""
        model = User
        fields = [
            'username',
            'email'
        ]


class ProfileUpdateForm(forms.ModelForm):
    """Form for updating user profile information."""
    class Meta:
        """Meta options for the ProfileUpdateForm."""
        model = Profile
        fields = [
            'telephone',
            'email',
            'first_name',
            'last_name',
            'profile_picture'
        ]


OPENING_SIGN_WIDGET = forms.Select(attrs={"class": "form-select"})
OPENING_AMOUNT_WIDGET = forms.NumberInput(
    attrs={"class": "form-control", "placeholder": "0.00", "step": "0.01", "min": "0"}
)


def _signed_opening_initial(balance):
    value = _d(balance)
    return {
        "opening_sign": "+" if value >= 0 else "-",
        "opening_amount": abs(value),
    }


def _signed_opening_value(sign, amount):
    value = abs(_d(amount))
    return value if sign == "+" else -value


class CustomerForm(forms.ModelForm):
    """Form for creating/updating customer information."""

    opening_sign = forms.ChoiceField(
        choices=[("+", "Receivable (+)"), ("-", "Payable (−)")],
        initial="+",
        required=False,
        label="Opening balance type",
        widget=OPENING_SIGN_WIDGET,
        help_text="Receivable: customer owes you. Payable: customer credit.",
    )
    opening_amount = forms.DecimalField(
        required=False,
        min_value=Decimal("0"),
        label="Opening balance amount (Rs)",
        widget=OPENING_AMOUNT_WIDGET,
    )

    class Meta:
        model = Customer
        fields = [
            'first_name',
            'last_name',
            'address',
            'email',
            'phone',
            'pan_number',
            'loyalty_points',
        ]
        widgets = {
            'first_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter first name'
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter last name'
            }),
            'address': forms.Textarea(attrs={
                'class': 'form-control',
                'placeholder': 'Enter address',
                'rows': 3
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter email'
            }),
            'phone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter phone number'
            }),
            'pan_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'PAN / tax ID (optional)',
            }),
            'loyalty_points': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter loyalty points'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            initial = _signed_opening_initial(self.instance.opening_balance)
            self.fields["opening_sign"].initial = initial["opening_sign"]
            self.fields["opening_amount"].initial = initial["opening_amount"]

    def save(self, commit=True):
        instance = super().save(commit=False)
        amount = self.cleaned_data.get("opening_amount")
        if amount in (None, ""):
            instance.opening_balance = Decimal("0")
        else:
            instance.opening_balance = _signed_opening_value(
                self.cleaned_data.get("opening_sign", "+"),
                amount,
            )
        if commit:
            instance.save()
        return instance


class VendorForm(forms.ModelForm):
    """Form for creating/updating vendor information."""

    opening_sign = forms.ChoiceField(
        choices=[("+", "Payable (+)"), ("-", "Receivable (−)")],
        initial="+",
        required=False,
        label="Opening balance type",
        widget=OPENING_SIGN_WIDGET,
        help_text="Payable: you owe supplier. Receivable: supplier credit.",
    )
    opening_amount = forms.DecimalField(
        required=False,
        min_value=Decimal("0"),
        label="Opening balance amount (Rs)",
        widget=OPENING_AMOUNT_WIDGET,
    )

    class Meta:
        model = Vendor
        fields = ['name', 'phone_number', 'pan_number', 'vat_number', 'address']
        widgets = {
            'name': forms.TextInput(
                attrs={'class': 'form-control', 'placeholder': 'Vendor Name'}
            ),
            'phone_number': forms.TextInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': '+977 98XXXXXXXX or 01-XXXXXXX',
                }
            ),
            'pan_number': forms.TextInput(
                attrs={'class': 'form-control', 'placeholder': 'PAN / tax ID (optional)'}
            ),
            'vat_number': forms.TextInput(
                attrs={'class': 'form-control', 'placeholder': 'VAT registration no. (optional)'}
            ),
            'address': forms.TextInput(
                attrs={'class': 'form-control', 'placeholder': 'Address'}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            initial = _signed_opening_initial(self.instance.opening_balance)
            self.fields["opening_sign"].initial = initial["opening_sign"]
            self.fields["opening_amount"].initial = initial["opening_amount"]

    def save(self, commit=True):
        instance = super().save(commit=False)
        amount = self.cleaned_data.get("opening_amount")
        if amount in (None, ""):
            instance.opening_balance = Decimal("0")
        else:
            instance.opening_balance = _signed_opening_value(
                self.cleaned_data.get("opening_sign", "+"),
                amount,
            )
        if commit:
            instance.save()
        return instance


class VendorBrandForm(forms.ModelForm):
    """Add a brand under a supplier."""

    class Meta:
        model = Brand
        fields = ['name', 'notes']
        labels = {
            'name': 'Brand name',
            'notes': 'Notes (optional)',
        }
        widgets = {
            'name': forms.TextInput(
                attrs={'class': 'form-control', 'placeholder': 'e.g. Samsung, Nike'}
            ),
            'notes': forms.TextInput(
                attrs={'class': 'form-control', 'placeholder': 'Optional note'}
            ),
        }


class LogisticsForm(forms.ModelForm):
    """Form for creating/updating logistics company information."""
    class Meta:
        model = Logistics
        fields = [
            'name',
            'contact_person',
            'phone_number',
            'email',
            'address',
            'tracking_url',
            'is_active'
        ]
        widgets = {
            'name': forms.TextInput(
                attrs={'class': 'form-control', 'placeholder': 'Logistics Company Name'}
            ),
            'contact_person': forms.TextInput(
                attrs={'class': 'form-control', 'placeholder': 'Contact Person Name'}
            ),
            'phone_number': forms.TextInput(
                attrs={'class': 'form-control', 'placeholder': '+977 98XXXXXXXX or 01-XXXXXXX'}
            ),
            'email': forms.EmailInput(
                attrs={'class': 'form-control', 'placeholder': 'Email Address'}
            ),
            'address': forms.Textarea(
                attrs={'class': 'form-control', 'placeholder': 'Company Address', 'rows': 3}
            ),
            'tracking_url': forms.URLInput(
                attrs={'class': 'form-control', 'placeholder': 'https://example.com/track/{tracking_number}'}
            ),
            'is_active': forms.CheckboxInput(
                attrs={'class': 'form-check-input'}
            ),
        }
        labels = {
            'is_active': 'Active',
        }


class SignedOpeningBalanceForm(forms.Form):
    """Signed opening balance: + receivable/payable, − opposite credit."""

    opening_sign = forms.ChoiceField(
        choices=[("+", "Receivable / Payable (+)"), ("-", "Payable / Receivable (−)")],
        initial="+",
        label="Type",
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )
    opening_amount = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0"),
        label="Amount (Rs)",
        widget=forms.NumberInput(
            attrs={"class": "form-control form-control-sm", "step": "0.01", "min": "0"}
        ),
    )

    def opening_balance_value(self):
        return _signed_opening_value(
            self.cleaned_data["opening_sign"],
            self.cleaned_data["opening_amount"],
        )


class CustomerAccountTransactionForm(forms.Form):
    transaction_date = _transaction_date_field()
    transaction_type = forms.ChoiceField(
        choices=[
            ("sale_in", "Sale in (add receivable)"),
            ("payment_in", "Payment in (receive money)"),
        ],
        label="Transaction",
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )
    amount = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.01"),
        label="Amount (Rs)",
        widget=forms.NumberInput(attrs={"class": "form-control form-control-sm", "step": "0.01"}),
    )
    reference = forms.CharField(
        required=False,
        label="Reference",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    )
    method = forms.ChoiceField(
        choices=PAYMENT_METHOD_CHOICES,
        initial="cash",
        label="Method",
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )
    notes = forms.CharField(
        required=False,
        label="Notes",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.initial.get("transaction_date"):
            self.initial["transaction_date"] = timezone.localtime(timezone.now()).strftime(
                DATETIME_LOCAL_FORMAT
            )


class VendorAccountTransactionForm(forms.Form):
    transaction_date = _transaction_date_field()
    transaction_type = forms.ChoiceField(
        choices=[
            ("bill_in", "Bill in (add payable)"),
            ("payment_out", "Payment out (pay supplier)"),
        ],
        label="Transaction",
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )
    amount = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.01"),
        label="Amount (Rs)",
        widget=forms.NumberInput(attrs={"class": "form-control form-control-sm", "step": "0.01"}),
    )
    reference = forms.CharField(
        required=False,
        label="Bill / reference",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    )
    amount_paid = forms.DecimalField(
        required=False,
        min_value=Decimal("0"),
        label="Paid now (Rs)",
        widget=forms.NumberInput(attrs={"class": "form-control form-control-sm", "step": "0.01"}),
    )
    method = forms.ChoiceField(
        choices=PAYMENT_METHOD_CHOICES,
        initial="cash",
        label="Method",
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )
    notes = forms.CharField(
        required=False,
        label="Notes",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.initial.get("transaction_date"):
            self.initial["transaction_date"] = timezone.localtime(timezone.now()).strftime(
                DATETIME_LOCAL_FORMAT
            )


class SignedAdjustmentForm(forms.Form):
    """+ sets adjustment total, − applies credit to outstanding bills."""

    adjustment_sign = forms.ChoiceField(
        choices=[("+", "Increase (+)"), ("-", "Decrease (−)")],
        initial="+",
        label="Direction",
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )
    adjustment_amount = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0"),
        required=True,
        label="Amount (Rs)",
        widget=forms.NumberInput(
            attrs={"class": "form-control form-control-sm", "step": "0.01", "min": "0"}
        ),
    )


class PaymentEditForm(forms.Form):
    transaction_date = _transaction_date_field()
    amount = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.01"),
        label="Amount (Rs)",
        widget=forms.NumberInput(attrs={"class": "form-control form-control-sm", "step": "0.01"}),
    )
    method = forms.ChoiceField(
        choices=PAYMENT_METHOD_CHOICES,
        label="Method",
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )
    notes = forms.CharField(
        required=False,
        label="Notes",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    )


class CustomerPaymentForm(forms.Form):
    transaction_date = _transaction_date_field()
    sale = forms.ModelChoiceField(
        queryset=Sale.objects.none(),
        label="Sale bill",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    amount = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.01"),
        label="Amount (Rs)",
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    )
    method = forms.ChoiceField(
        choices=PAYMENT_METHOD_CHOICES,
        initial="cash",
        label="Payment method",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    notes = forms.CharField(
        required=False,
        label="Notes",
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )

    def __init__(self, *args, customer=None, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.initial.get("transaction_date"):
            self.initial["transaction_date"] = timezone.localtime(timezone.now()).strftime(
                DATETIME_LOCAL_FORMAT
            )
        if customer is not None:
            self.fields["sale"].queryset = (
                Sale.objects.filter(customer=customer)
                .order_by("-date_added")
            )
            self.fields["sale"].label_from_instance = (
                lambda s: f"#{s.id} — Rs {s.grand_total} (due Rs {s.amount_remaining})"
            )

    def clean(self):
        cleaned = super().clean()
        sale = cleaned.get("sale")
        amount = cleaned.get("amount")
        if sale and amount is not None:
            remaining = _d(sale.amount_remaining)
            if remaining > 0 and amount > remaining:
                self.add_error(
                    "amount",
                    f"Amount cannot exceed unpaid balance (Rs {remaining}).",
                )
        return cleaned


class VendorPaymentForm(forms.Form):
    transaction_date = _transaction_date_field()
    purchase = forms.ModelChoiceField(
        queryset=Purchase.objects.none(),
        label="Purchase bill",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    amount = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.01"),
        label="Amount (Rs)",
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    )
    method = forms.ChoiceField(
        choices=PAYMENT_METHOD_CHOICES,
        initial="cash",
        label="Payment method",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    notes = forms.CharField(
        required=False,
        label="Notes",
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )

    def __init__(self, *args, vendor=None, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.initial.get("transaction_date"):
            self.initial["transaction_date"] = timezone.localtime(timezone.now()).strftime(
                DATETIME_LOCAL_FORMAT
            )
        if vendor is not None:
            self.fields["purchase"].queryset = (
                Purchase.objects.filter(vendor=vendor)
                .order_by("-order_date")
            )
            self.fields["purchase"].label_from_instance = (
                lambda p: f"{p.display_bill_number} — Rs {p.net_amount} (due Rs {p.amount_remaining})"
            )

    def clean(self):
        cleaned = super().clean()
        purchase = cleaned.get("purchase")
        amount = cleaned.get("amount")
        if purchase and amount is not None:
            remaining = purchase.amount_remaining
            if amount > remaining and remaining >= 0:
                self.add_error(
                    "amount",
                    f"Amount cannot exceed outstanding (Rs {remaining}).",
                )
        return cleaned
