import django_filters
from django import forms
from .models import Sale, Purchase
from store.models import Item
from accounts.models import Customer, Vendor


class SaleFilter(django_filters.FilterSet):
    """
    Filter set for Sale model with date range and sorting.
    """
    customer = django_filters.ModelChoiceFilter(
        queryset=Customer.objects.all(),
        widget=forms.Select,
        field_name='customer'
    )
    customer_name = django_filters.CharFilter(
        field_name='customer__first_name',
        lookup_expr='icontains',
        widget=forms.TextInput,
        label='Customer Name'
    )
    date_from = django_filters.DateFilter(
        field_name='date_added',
        lookup_expr='gte',
        widget=forms.DateInput,
        label='Date From'
    )
    date_to = django_filters.DateFilter(
        field_name='date_added',
        lookup_expr='lte',
        widget=forms.DateInput,
        label='Date To'
    )
    min_total = django_filters.NumberFilter(
        field_name='grand_total',
        lookup_expr='gte',
        widget=forms.NumberInput,
        label='Min Total'
    )
    max_total = django_filters.NumberFilter(
        field_name='grand_total',
        lookup_expr='lte',
        widget=forms.NumberInput,
        label='Max Total'
    )
    ordering = django_filters.OrderingFilter(
        fields=(
            ('date_added', 'date_added'),
            ('grand_total', 'grand_total'),
            ('customer', 'customer'),
        ),
        widget=forms.Select
    )

    class Meta:
        model = Sale
        fields = ['customer', 'date_from', 'date_to']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set widget attrs after initialization
        self.filters['customer'].field.widget.attrs.update({'class': 'form-control'})
        self.filters['customer_name'].field.widget.attrs.update({'class': 'form-control', 'placeholder': 'Search by customer name'})
        self.filters['date_from'].field.widget.attrs.update({'class': 'form-control', 'type': 'date'})
        self.filters['date_to'].field.widget.attrs.update({'class': 'form-control', 'type': 'date'})
        self.filters['min_total'].field.widget.attrs.update({'class': 'form-control', 'placeholder': 'Min total', 'step': '0.01'})
        self.filters['max_total'].field.widget.attrs.update({'class': 'form-control', 'placeholder': 'Max total', 'step': '0.01'})
        self.filters['ordering'].field.widget.attrs.update({'class': 'form-control'})


class PurchaseFilter(django_filters.FilterSet):
    """
    Filter set for Purchase model with date range and sorting.
    """
    item = django_filters.ModelChoiceFilter(
        queryset=Item.objects.all(),
        widget=forms.Select,
        field_name="lines__item",
    )
    item_name = django_filters.CharFilter(
        field_name="lines__item__name",
        lookup_expr="icontains",
        widget=forms.TextInput,
        label="Item Name",
    )
    vendor = django_filters.ModelChoiceFilter(
        queryset=Vendor.objects.all(),
        widget=forms.Select,
        field_name='vendor'
    )
    receipt_status = django_filters.ChoiceFilter(
        choices=[("P", "Pending"), ("S", "Received")],
        widget=forms.Select,
        field_name='receipt_status'
    )
    payment_status = django_filters.ChoiceFilter(
        choices=[("U", "Unpaid"), ("T", "Partial"), ("D", "Paid"), ("X", "Overpaid")],
        widget=forms.Select,
        field_name='payment_status',
    )
    order_date_from = django_filters.DateFilter(
        field_name='order_date',
        lookup_expr='gte',
        widget=forms.DateInput,
        label='Order Date From'
    )
    order_date_to = django_filters.DateFilter(
        field_name='order_date',
        lookup_expr='lte',
        widget=forms.DateInput,
        label='Order Date To'
    )
    receipt_date_from = django_filters.DateFilter(
        field_name='receipt_date',
        lookup_expr='gte',
        widget=forms.DateInput,
        label='Receipt Date From'
    )
    receipt_date_to = django_filters.DateFilter(
        field_name='receipt_date',
        lookup_expr='lte',
        widget=forms.DateInput,
        label='Receipt Date To'
    )
    min_total = django_filters.NumberFilter(
        field_name='net_amount',
        lookup_expr='gte',
        widget=forms.NumberInput,
        label='Min Total'
    )
    max_total = django_filters.NumberFilter(
        field_name='net_amount',
        lookup_expr='lte',
        widget=forms.NumberInput,
        label='Max Total'
    )
    ordering = django_filters.OrderingFilter(
        fields=(
            ('order_date', 'order_date'),
            ('receipt_date', 'receipt_date'),
            ('net_amount', 'net_amount'),
            ('vendor', 'vendor'),
        ),
        widget=forms.Select
    )

    class Meta:
        model = Purchase
        fields = ['item', 'vendor', 'receipt_status', 'payment_status']

    def filter_queryset(self, queryset):
        return super().filter_queryset(queryset).distinct()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set widget attrs after initialization
        self.filters['item'].field.widget.attrs.update({'class': 'form-control'})
        self.filters['item_name'].field.widget.attrs.update({'class': 'form-control', 'placeholder': 'Search by item name'})
        self.filters['vendor'].field.widget.attrs.update({'class': 'form-control'})
        self.filters['receipt_status'].field.widget.attrs.update({'class': 'form-control'})
        self.filters['payment_status'].field.widget.attrs.update({'class': 'form-control'})
        self.filters['order_date_from'].field.widget.attrs.update({'class': 'form-control', 'type': 'date'})
        self.filters['order_date_to'].field.widget.attrs.update({'class': 'form-control', 'type': 'date'})
        self.filters['receipt_date_from'].field.widget.attrs.update({'class': 'form-control', 'type': 'date'})
        self.filters['receipt_date_to'].field.widget.attrs.update({'class': 'form-control', 'type': 'date'})
        self.filters['min_total'].field.widget.attrs.update({'class': 'form-control', 'placeholder': 'Min total', 'step': '0.01'})
        self.filters['max_total'].field.widget.attrs.update({'class': 'form-control', 'placeholder': 'Max total', 'step': '0.01'})
        self.filters['ordering'].field.widget.attrs.update({'class': 'form-control'})
