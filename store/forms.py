from django import forms
from django.forms import inlineformset_factory
from .models import Item, Category, Delivery, ProductVariation, StockAdjustmentLog
from accounts.models import Brand, Logistics, Vendor


class ItemForm(forms.ModelForm):
    """
    A form for creating or updating an Item in the inventory.
    Flow: supplier → brand → category → product name.
    """

    class Meta:
        model = Item
        fields = [
            'vendor',
            'brand',
            'category',
            'name',
            'hs_code',
            'sku',
            'description',
            'quantity',
            'cost_price',
            'price',
            'low_stock_threshold',
            'expiring_date',
            'image',
        ]
        widgets = {
            'vendor': forms.Select(attrs={'class': 'form-control', 'id': 'id_vendor'}),
            'brand': forms.Select(attrs={'class': 'form-control', 'id': 'id_brand'}),
            'category': forms.Select(attrs={'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Product name'}),
            'sku': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Optional SKU'}),
            'hs_code': forms.TextInput(
                attrs={'class': 'form-control', 'placeholder': 'e.g. 8471.30'}
            ),
            'description': forms.Textarea(
                attrs={
                    'class': 'form-control',
                    'rows': 2
                }
            ),
            'quantity': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
            }),
            'cost_price': forms.NumberInput(
                attrs={
                    'class': 'form-control',
                    'step': '0.01',
                    'placeholder': '0.00'
                }
            ),
            'price': forms.NumberInput(
                attrs={
                    'class': 'form-control',
                    'step': '0.01'
                }
            ),
            'low_stock_threshold': forms.NumberInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': '10'
                }
            ),
            'expiring_date': forms.DateTimeInput(
                attrs={
                    'class': 'form-control',
                    'type': 'datetime-local'
                }
            ),
            'image': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*'
            }),
        }
        labels = {
            'vendor': 'Supplier',
            'brand': 'Brand',
            'image': 'Product Image',
            'cost_price': 'Cost Price (Rs)',
            'price': 'Selling Price (Rs)',
            'low_stock_threshold': 'Low Stock Alert Threshold',
            'quantity': 'Total stock (base + all variant quantities)',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['vendor'].queryset = Vendor.objects.order_by('name')
        self.fields['vendor'].required = True
        self.fields['brand'].required = True
        self.fields['category'].required = True
        self.fields['brand'].queryset = Brand.objects.none()

        vendor_id = None
        if self.instance.pk and self.instance.vendor_id:
            vendor_id = self.instance.vendor_id
        if self.data.get(self.add_prefix('vendor')):
            vendor_id = self.data.get(self.add_prefix('vendor'))
        if vendor_id:
            self.fields['brand'].queryset = Brand.objects.filter(
                vendor_id=vendor_id,
                is_active=True,
            ).order_by('name')

    def clean(self):
        cleaned = super().clean()
        vendor = cleaned.get('vendor')
        brand = cleaned.get('brand')
        if vendor and brand and brand.vendor_id != vendor.id:
            self.add_error('brand', 'This brand does not belong to the selected supplier.')
        if vendor and not brand:
            self.add_error('brand', 'Select a brand for this supplier.')
        return cleaned


class ProductVariationForm(forms.ModelForm):
    """
    A form for creating or updating product variations.
    """
    class Meta:
        model = ProductVariation
        fields = [
            'variation_type',
            'name',
            'value',
            'quantity',
            'price_adjustment',
            'is_active'
        ]
        widgets = {
            'variation_type': forms.Select(attrs={
                'class': 'form-control variation-type'
            }),
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Red, Large, Cotton'
            }),
            'value': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Optional: #FF0000, 10x10, etc.'
            }),
            'quantity': forms.NumberInput(attrs={
                'class': 'form-control'
            }),
            'price_adjustment': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'placeholder': '0.00'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }
        labels = {
            'variation_type': 'Type',
            'name': 'Name',
            'value': 'Value (Optional)',
            'quantity': 'Quantity',
            'price_adjustment': 'Price Adjustment',
            'is_active': 'Active',
        }


# Create formset for product variations
ProductVariationFormSet = inlineformset_factory(
    Item,
    ProductVariation,
    form=ProductVariationForm,
    extra=1,
    can_delete=True,
    min_num=0,
    validate_min=False
)


class CategoryForm(forms.ModelForm):
    """
    A form for creating or updating category.
    """
    class Meta:
        model = Category
        fields = ['name']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter category name',
                'aria-label': 'Category Name'
            }),
        }
        labels = {
            'name': 'Category Name',
        }


class DeliveryForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filter to show only active logistics companies
        self.fields['logistics'].queryset = Logistics.objects.filter(is_active=True)
        # Make logistics field optional
        self.fields['logistics'].required = False
        self.fields['logistics'].empty_label = "Select logistics company (optional)"
    
    class Meta:
        model = Delivery
        fields = [
            'item',
            'customer_name',
            'phone_number',
            'location',
            'date',
            'logistics',
            'tracking_number',
            'is_delivered'
        ]
        widgets = {
            'item': forms.Select(attrs={
                'class': 'form-control',
                'placeholder': 'Select item',
            }),
            'customer_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter customer name',
            }),
            'phone_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '+977 98XXXXXXXX or 01-XXXXXXX',
            }),
            'location': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter delivery location',
            }),
            'date': forms.DateTimeInput(attrs={
                'class': 'form-control',
                'placeholder': 'Select delivery date and time',
                'type': 'datetime-local'
            }),
            'logistics': forms.Select(attrs={
                'class': 'form-control',
                'placeholder': 'Select logistics company',
            }),
            'tracking_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter tracking number',
            }),
            'is_delivered': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
                'label': 'Mark as delivered',
            }),
        }
        labels = {
            'logistics': 'Logistics Company',
            'tracking_number': 'Tracking Number',
        }


class StockAdjustmentForm(forms.Form):
    """Manual stock correction on a product or variant."""

    MODE_CHOICES = StockAdjustmentLog.MODE_CHOICES

    mode = forms.ChoiceField(
        choices=MODE_CHOICES,
        widget=forms.Select(attrs={"class": "form-select"}),
        label="Action",
    )
    quantity = forms.IntegerField(
        min_value=0,
        widget=forms.NumberInput(attrs={"class": "form-control", "min": "0"}),
        label="Quantity",
    )
    variation = forms.ModelChoiceField(
        queryset=ProductVariation.objects.none(),
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
        label="Variant (optional — base stock if empty)",
    )
    reason = forms.CharField(
        max_length=255,
        required=False,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "e.g. Stock count, damage, correction"}
        ),
        label="Reason",
    )

    def __init__(self, item, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.item = item
        self.fields["variation"].queryset = item.variations.filter(is_active=True)

    def clean(self):
        cleaned = super().clean()
        mode = cleaned.get("mode")
        qty = cleaned.get("quantity")
        if mode in ("add", "remove") and (qty is None or qty <= 0):
            self.add_error("quantity", "Enter a quantity greater than zero.")
        return cleaned
