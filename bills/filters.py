import django_filters
from django import forms
from .models import Bill


class BillFilter(django_filters.FilterSet):
    """
    Filter set for Bill model with date range and sorting.
    """
    institution_name = django_filters.CharFilter(
        lookup_expr='icontains',
        widget=forms.TextInput
    )
    email = django_filters.CharFilter(
        lookup_expr='icontains',
        widget=forms.TextInput
    )
    payment_details = django_filters.CharFilter(
        lookup_expr='icontains',
        widget=forms.TextInput
    )
    status = django_filters.BooleanFilter(
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
    min_amount = django_filters.NumberFilter(
        field_name='amount',
        lookup_expr='gte',
        widget=forms.NumberInput
    )
    max_amount = django_filters.NumberFilter(
        field_name='amount',
        lookup_expr='lte',
        widget=forms.NumberInput
    )
    ordering = django_filters.OrderingFilter(
        fields=(
            ('date', 'date'),
            ('amount', 'amount'),
            ('institution_name', 'institution_name'),
            ('status', 'status'),
        ),
        widget=forms.Select
    )

    class Meta:
        model = Bill
        fields = ['institution_name', 'email', 'status']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set widget attrs after initialization
        self.filters['institution_name'].field.widget.attrs.update({'class': 'form-control', 'placeholder': 'Search by institution name'})
        self.filters['email'].field.widget.attrs.update({'class': 'form-control', 'placeholder': 'Search by email'})
        self.filters['payment_details'].field.widget.attrs.update({'class': 'form-control', 'placeholder': 'Search by payment details'})
        self.filters['status'].field.widget.attrs.update({'class': 'form-control'})
        self.filters['status'].field.widget.choices = [('', 'All'), ('True', 'Paid'), ('False', 'Pending')]
        self.filters['date_from'].field.widget.attrs.update({'class': 'form-control', 'type': 'date'})
        self.filters['date_to'].field.widget.attrs.update({'class': 'form-control', 'type': 'date'})
        self.filters['min_amount'].field.widget.attrs.update({'class': 'form-control', 'placeholder': 'Min amount', 'step': '0.01'})
        self.filters['max_amount'].field.widget.attrs.update({'class': 'form-control', 'placeholder': 'Max amount', 'step': '0.01'})
        self.filters['ordering'].field.widget.attrs.update({'class': 'form-control'})
