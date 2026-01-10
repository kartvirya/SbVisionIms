import django_filters
from django import forms
from .models import Invoice
from store.models import Item


class InvoiceFilter(django_filters.FilterSet):
    """
    Filter set for Invoice model with date range and sorting.
    """
    customer_name = django_filters.CharFilter(
        lookup_expr='icontains',
        widget=forms.TextInput
    )
    contact_number = django_filters.CharFilter(
        lookup_expr='icontains',
        widget=forms.TextInput
    )
    item = django_filters.ModelChoiceFilter(
        queryset=Item.objects.all(),
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
    min_total = django_filters.NumberFilter(
        field_name='grand_total',
        lookup_expr='gte',
        widget=forms.NumberInput
    )
    max_total = django_filters.NumberFilter(
        field_name='grand_total',
        lookup_expr='lte',
        widget=forms.NumberInput
    )
    ordering = django_filters.OrderingFilter(
        fields=(
            ('date', 'date'),
            ('grand_total', 'grand_total'),
            ('customer_name', 'customer_name'),
        ),
        widget=forms.Select
    )

    class Meta:
        model = Invoice
        fields = ['customer_name', 'contact_number', 'item']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set widget attrs after initialization
        self.filters['customer_name'].field.widget.attrs.update({'class': 'form-control', 'placeholder': 'Search by customer name'})
        self.filters['contact_number'].field.widget.attrs.update({'class': 'form-control', 'placeholder': 'Search by contact number'})
        self.filters['item'].field.widget.attrs.update({'class': 'form-control'})
        self.filters['date_from'].field.widget.attrs.update({'class': 'form-control', 'type': 'date'})
        self.filters['date_to'].field.widget.attrs.update({'class': 'form-control', 'type': 'date'})
        self.filters['min_total'].field.widget.attrs.update({'class': 'form-control', 'placeholder': 'Min total', 'step': '0.01'})
        self.filters['max_total'].field.widget.attrs.update({'class': 'form-control', 'placeholder': 'Max total', 'step': '0.01'})
        self.filters['ordering'].field.widget.attrs.update({'class': 'form-control'})
