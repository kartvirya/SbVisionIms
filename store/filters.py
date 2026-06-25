import django_filters
from django import forms
from .models import Item, Category, Delivery
from accounts.models import Brand, Vendor, Logistics


class ProductFilter(django_filters.FilterSet):
    """
    Filter set for Item model with date range and sorting.
    """
    name = django_filters.CharFilter(
        lookup_expr='icontains',
        widget=forms.TextInput
    )
    category = django_filters.ModelChoiceFilter(
        queryset=Category.objects.all(),
        widget=forms.Select
    )
    vendor = django_filters.ModelChoiceFilter(
        queryset=Vendor.objects.all(),
        widget=forms.Select
    )
    brand = django_filters.ModelChoiceFilter(
        queryset=Brand.objects.filter(is_active=True).order_by("name"),
        widget=forms.Select,
    )
    min_price = django_filters.NumberFilter(
        field_name='price',
        lookup_expr='gte',
        widget=forms.NumberInput
    )
    max_price = django_filters.NumberFilter(
        field_name='price',
        lookup_expr='lte',
        widget=forms.NumberInput
    )
    min_quantity = django_filters.NumberFilter(
        field_name='quantity',
        lookup_expr='gte',
        widget=forms.NumberInput
    )
    expiring_date = django_filters.DateFilter(
        field_name='expiring_date',
        lookup_expr='gte',
        widget=forms.DateInput
    )
    ordering = django_filters.OrderingFilter(
        fields=(
            ('name', 'name'),
            ('price', 'price'),
            ('quantity', 'quantity'),
            ('expiring_date', 'expiring_date'),
        ),
        widget=forms.Select
    )

    class Meta:
        model = Item
        fields = ['name', 'category', 'vendor', 'brand']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set widget attrs after initialization
        self.filters['name'].field.widget.attrs.update({'class': 'form-control', 'placeholder': 'Search by name'})
        self.filters['category'].field.widget.attrs.update({'class': 'form-control'})
        self.filters['vendor'].field.widget.attrs.update({'class': 'form-control'})
        self.filters['brand'].field.widget.attrs.update({'class': 'form-control'})
        self.filters['min_price'].field.widget.attrs.update({'class': 'form-control', 'placeholder': 'Min price', 'step': '0.01'})
        self.filters['max_price'].field.widget.attrs.update({'class': 'form-control', 'placeholder': 'Max price', 'step': '0.01'})
        self.filters['min_quantity'].field.widget.attrs.update({'class': 'form-control', 'placeholder': 'Min quantity'})
        self.filters['expiring_date'].field.widget.attrs.update({'class': 'form-control', 'type': 'date'})
        self.filters['ordering'].field.widget.attrs.update({'class': 'form-control'})


class DeliveryFilter(django_filters.FilterSet):
    """
    Filter set for Delivery model with date range and sorting.
    """
    customer_name = django_filters.CharFilter(
        lookup_expr='icontains',
        widget=forms.TextInput
    )
    phone_number = django_filters.CharFilter(
        lookup_expr='icontains',
        widget=forms.TextInput
    )
    location = django_filters.CharFilter(
        lookup_expr='icontains',
        widget=forms.TextInput
    )
    logistics = django_filters.ModelChoiceFilter(
        queryset=Logistics.objects.filter(is_active=True),
        widget=forms.Select
    )
    is_delivered = django_filters.BooleanFilter(
        widget=forms.Select
    )
    date_from = django_filters.DateFilter(
        field_name='date',
        lookup_expr='gte',
        widget=forms.DateInput
    )
    date_to = django_filters.DateFilter(
        field_name='date',
        lookup_expr='lte',
        widget=forms.DateInput
    )
    ordering = django_filters.OrderingFilter(
        fields=(
            ('date', 'date'),
            ('customer_name', 'customer_name'),
            ('is_delivered', 'is_delivered'),
        ),
        widget=forms.Select
    )

    class Meta:
        model = Delivery
        fields = ['customer_name', 'phone_number', 'location', 'logistics', 'is_delivered']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set widget attrs after initialization
        self.filters['customer_name'].field.widget.attrs.update({'class': 'form-control', 'placeholder': 'Search by customer name'})
        self.filters['phone_number'].field.widget.attrs.update({'class': 'form-control', 'placeholder': 'Search by phone'})
        self.filters['location'].field.widget.attrs.update({'class': 'form-control', 'placeholder': 'Search by location'})
        self.filters['logistics'].field.widget.attrs.update({'class': 'form-control'})
        self.filters['is_delivered'].field.widget.attrs.update({'class': 'form-control'})
        self.filters['is_delivered'].field.widget.choices = [('', 'All'), ('True', 'Delivered'), ('False', 'Pending')]
        self.filters['date_from'].field.widget.attrs.update({'class': 'form-control', 'type': 'date'})
        self.filters['date_to'].field.widget.attrs.update({'class': 'form-control', 'type': 'date'})
        self.filters['ordering'].field.widget.attrs.update({'class': 'form-control'})
