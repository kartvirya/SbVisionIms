from django import forms
from django.forms import inlineformset_factory
from .models import Item, Category, Delivery, ProductVariation
from accounts.models import Logistics


class ItemForm(forms.ModelForm):
    """
    A form for creating or updating an Item in the inventory.
    """
    class Meta:
        model = Item
        fields = [
            'name',
            'description',
            'category',
            'quantity',
            'cost_price',
            'price',
            'low_stock_threshold',
            'expiring_date',
            'vendor',
            'image'
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(
                attrs={
                    'class': 'form-control',
                    'rows': 2
                }
            ),
            'category': forms.Select(attrs={'class': 'form-control'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control'}),
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
            'vendor': forms.Select(attrs={'class': 'form-control'}),
            'image': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*'
            }),
        }
        labels = {
            'image': 'Product Image',
            'cost_price': 'Cost Price (Rs)',
            'price': 'Selling Price (Rs)',
            'low_stock_threshold': 'Low Stock Alert Threshold',
        }


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
