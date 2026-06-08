from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from decimal import Decimal

from django.utils import timezone

from transactions.models import PAYMENT_METHOD_CHOICES, CustomerPayment, Purchase, Sale, VendorPayment

from .models import Profile, Customer, Vendor, Logistics


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


class CustomerForm(forms.ModelForm):
    """Form for creating/updating customer information."""
    class Meta:
        model = Customer
        fields = [
            'first_name',
            'last_name',
            'address',
            'email',
            'phone',
            'opening_balance',
            'loyalty_points'
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
            'opening_balance': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': '0.00',
                'step': '0.01',
            }),
            'loyalty_points': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter loyalty points'
            }),
        }


class VendorForm(forms.ModelForm):
    """Form for creating/updating vendor information."""
    class Meta:
        model = Vendor
        fields = ['name', 'phone_number', 'address', 'opening_balance']
        widgets = {
            'name': forms.TextInput(
                attrs={'class': 'form-control', 'placeholder': 'Vendor Name'}
            ),
            'phone_number': forms.NumberInput(
                attrs={'class': 'form-control', 'placeholder': 'Phone Number'}
            ),
            'address': forms.TextInput(
                attrs={'class': 'form-control', 'placeholder': 'Address'}
            ),
            'opening_balance': forms.NumberInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': '0.00',
                    'step': '0.01',
                }
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


class OpeningBalanceForm(forms.Form):
    opening_balance = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        label="Opening balance (Rs)",
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    )


class SignedAdjustmentForm(forms.Form):
    """+ increases balance owed, − reduces it (credit)."""

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
        label="Amount (Rs)",
        widget=forms.NumberInput(
            attrs={"class": "form-control form-control-sm", "step": "0.01", "min": "0"}
        ),
    )


class PaymentEditForm(forms.Form):
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


def _d(value):
    return Decimal(str(value or 0))


class VendorPaymentForm(forms.Form):
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
