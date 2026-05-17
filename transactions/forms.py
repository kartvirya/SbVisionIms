from decimal import Decimal

from django import forms
from django.forms import inlineformset_factory
from django.utils import timezone

from accounts.models import Vendor
from store.models import Item
from .models import Purchase, PurchaseLine


class BootstrapMixin:
    """Add Bootstrap classes to form fields (works with Form and ModelForm)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            css = "form-select" if isinstance(field.widget, forms.Select) else "form-control"
            field.widget.attrs.setdefault("class", css)


class PurchaseForm(BootstrapMixin, forms.ModelForm):
    """Purchase header: vendor bill, dates, tax, and payment."""

    class Meta:
        model = Purchase
        fields = [
            "vendor",
            "bill_number",
            "order_date",
            "receipt_status",
            "receipt_date",
            "description",
            "discount_amount",
            "vat_percentage",
            "vat_amount",
            "amount_paid",
        ]
        labels = {
            "vendor": "Supplier / vendor",
            "bill_number": "Supplier bill number",
            "order_date": "Billed date",
            "receipt_status": "Stock receipt",
            "receipt_date": "Goods received date",
            "description": "Notes",
            "discount_amount": "Discount (Rs)",
            "vat_percentage": "VAT %",
            "vat_amount": "VAT amount (Rs)",
            "amount_paid": "Amount paid now (Rs)",
        }
        help_texts = {
            "bill_number": "Invoice or bill reference from the supplier.",
            "order_date": "Date on the supplier's bill.",
            "receipt_status": "Received posts stock into your shop inventory.",
            "receipt_date": "When goods physically arrived (optional if pending).",
            "amount_paid": "Cash or bank paid to the supplier on this bill.",
        }
        widgets = {
            "order_date": forms.DateTimeInput(
                attrs={"type": "datetime-local", "class": "form-control"},
                format="%Y-%m-%dT%H:%M",
            ),
            "receipt_date": forms.DateTimeInput(
                attrs={"type": "datetime-local", "class": "form-control"},
                format="%Y-%m-%dT%H:%M",
            ),
            "description": forms.Textarea(attrs={"rows": 2, "placeholder": "Optional notes"}),
            "receipt_status": forms.Select(attrs={"class": "form-select"}),
            "vendor": forms.Select(attrs={"class": "form-select", "id": "id_vendor"}),
            "discount_amount": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
            "vat_percentage": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
            "vat_amount": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
            "amount_paid": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["vendor"].queryset = self.fields["vendor"].queryset.order_by("name")
        datetime_local = ["%Y-%m-%dT%H:%M"]
        for fn in ("order_date", "receipt_date"):
            self.fields[fn].input_formats = datetime_local
        self.fields["order_date"].required = True
        if self.instance and self.instance.pk and self.instance.vendor_payments.exists():
            self.fields["amount_paid"].disabled = True
            self.fields["amount_paid"].help_text = "Total from vendor payment records in admin."
        if self.instance and self.instance.pk:
            for field_name in ("order_date", "receipt_date"):
                dt = getattr(self.instance, field_name, None)
                if dt:
                    self.initial[field_name] = timezone.localtime(dt).strftime("%Y-%m-%dT%H:%M")
        elif not self.initial.get("order_date"):
            self.initial["order_date"] = timezone.localtime(timezone.now()).strftime("%Y-%m-%dT%H:%M")

    def clean(self):
        cleaned_data = super().clean()
        amount_paid = cleaned_data.get("amount_paid") or 0
        if hasattr(amount_paid, "__lt__") and amount_paid < 0:
            self.add_error("amount_paid", "Amount paid cannot be negative.")
        if cleaned_data.get("receipt_status") == "S" and not cleaned_data.get("receipt_date"):
            cleaned_data["receipt_date"] = timezone.now()
        return cleaned_data


class PurchaseLineForm(BootstrapMixin, forms.ModelForm):
    """One product line on a purchase bill."""

    class Meta:
        model = PurchaseLine
        fields = ("item", "quantity", "unit_price")
        labels = {
            "item": "Product",
            "quantity": "Qty purchased",
            "unit_price": "Unit cost (Rs)",
        }
        widgets = {
            "item": forms.Select(attrs={"class": "form-select item-select"}),
            "quantity": forms.NumberInput(attrs={"min": 1, "step": 1, "class": "form-control line-qty"}),
            "unit_price": forms.NumberInput(
                attrs={"step": "0.01", "min": "0", "class": "form-control line-unit-price"}
            ),
        }

    def __init__(self, *args, vendor_id=None, **kwargs):
        super().__init__(*args, **kwargs)
        qs = Item.objects.select_related("vendor", "category").order_by("name")
        if vendor_id:
            qs = qs.filter(vendor_id=vendor_id)
        self.fields["item"].queryset = qs
        self.fields["item"].label_from_instance = lambda obj: (
            f"{obj.name} — stock: {obj.quantity}, cost: {obj.cost_price:.2f}"
        )
        if self.instance and self.instance.pk and self.instance.item_id:
            if not self.initial.get("unit_price") and self.instance.unit_price:
                pass
            elif self.instance.unit_price == 0 and self.instance.item.cost_price:
                self.initial.setdefault("unit_price", self.instance.item.cost_price)


class BasePurchaseLineFormSet(forms.BaseInlineFormSet):
    def __init__(self, *args, vendor_id=None, **kwargs):
        self.vendor_id = vendor_id
        super().__init__(*args, **kwargs)

    def _construct_form(self, i, **kwargs):
        kwargs["vendor_id"] = self.vendor_id
        return super()._construct_form(i, **kwargs)


class PayablesQuickEntryForm(BootstrapMixin, forms.Form):
    """Quick supplier bill entry from the payables book."""

    vendor = forms.ModelChoiceField(
        queryset=Vendor.objects.order_by("name"),
        label="Supplier",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    bill_number = forms.CharField(
        max_length=64,
        required=False,
        label="Bill number",
        widget=forms.TextInput(attrs={"placeholder": "Supplier invoice #"}),
    )
    order_date = forms.DateTimeField(
        label="Billed date",
        required=False,
        widget=forms.DateTimeInput(
            attrs={"type": "datetime-local", "class": "form-control"},
            format="%Y-%m-%dT%H:%M",
        ),
        input_formats=["%Y-%m-%dT%H:%M"],
    )
    net_amount = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.01"),
        label="Bill amount (Rs)",
        widget=forms.NumberInput(attrs={"step": "0.01", "min": "0.01"}),
    )
    amount_paid = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=0,
        required=False,
        initial=0,
        label="Amount paid now (Rs)",
        widget=forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
    )
    description = forms.CharField(
        required=False,
        label="Notes",
        widget=forms.TextInput(attrs={"placeholder": "Optional"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.initial.get("order_date"):
            self.initial["order_date"] = timezone.localtime(timezone.now()).strftime(
                "%Y-%m-%dT%H:%M"
            )

    def clean(self):
        cleaned = super().clean()
        net_amount = cleaned.get("net_amount") or 0
        amount_paid = cleaned.get("amount_paid") or 0
        if amount_paid > net_amount:
            self.add_error("amount_paid", "Paid amount cannot exceed bill amount.")
        return cleaned


PurchaseLineFormSet = inlineformset_factory(
    Purchase,
    PurchaseLine,
    form=PurchaseLineForm,
    formset=BasePurchaseLineFormSet,
    extra=3,
    min_num=1,
    validate_min=True,
    can_delete=True,
)
