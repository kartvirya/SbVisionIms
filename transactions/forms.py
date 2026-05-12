from django import forms
from django.forms import inlineformset_factory

from .models import Purchase, PurchaseLine


class BootstrapMixin(forms.ModelForm):
    """
    A mixin to add Bootstrap classes to form fields.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")


class PurchaseForm(BootstrapMixin, forms.ModelForm):
    """
    Purchase header fields (lines use PurchaseLineFormSet).
    """

    class Meta:
        model = Purchase
        fields = [
            "vendor",
            "description",
            "discount_amount",
            "vat_percentage",
            "vat_amount",
            "receipt_date",
            "receipt_status",
            "amount_paid",
        ]
        widgets = {
            "receipt_date": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "description": forms.Textarea(attrs={"rows": 1, "cols": 40}),
            "receipt_status": forms.Select(attrs={"class": "form-control"}),
            "discount_amount": forms.NumberInput(attrs={"step": "0.01"}),
            "vat_percentage": forms.NumberInput(attrs={"step": "0.01"}),
            "vat_amount": forms.NumberInput(attrs={"step": "0.01"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.vendor_payments.exists():
            self.fields["amount_paid"].disabled = True
            self.fields["amount_paid"].help_text = "Derived from Vendor payment entries."

    def clean(self):
        cleaned_data = super().clean()
        amount_paid = cleaned_data.get("amount_paid") or 0
        if hasattr(amount_paid, "__lt__"):
            if amount_paid < 0:
                self.add_error("amount_paid", "Amount paid cannot be negative.")
        return cleaned_data


class PurchaseLineForm(BootstrapMixin, forms.ModelForm):
    """One stock line on a purchase."""

    class Meta:
        model = PurchaseLine
        fields = ("item", "quantity", "unit_price")
        widgets = {
            "quantity": forms.NumberInput(attrs={"min": 1, "step": 1}),
            "unit_price": forms.NumberInput(attrs={"step": "0.01"}),
        }


PurchaseLineFormSet = inlineformset_factory(
    Purchase,
    PurchaseLine,
    form=PurchaseLineForm,
    extra=1,
    min_num=1,
    validate_min=True,
    can_delete=True,
)
