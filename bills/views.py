# Django core imports
from django.urls import reverse

# Class-based views
from django.views.generic import (
    ListView,
    CreateView,
    UpdateView,
    DeleteView
)

# Authentication and permissions
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin

# Third-party packages
from django_tables2.export.views import ExportMixin

# Local app imports
from .models import Bill
from accounts.models import Profile
from .filters import BillFilter


class BillListView(LoginRequiredMixin, ListView):
    """View for listing bills with filtering."""
    model = Bill
    template_name = 'bills/bill_list.html'
    context_object_name = 'bills'
    paginate_by = 10
    filterset_class = BillFilter

    def get_queryset(self):
        queryset = super().get_queryset().order_by('-date')
        self.filterset = self.filterset_class(self.request.GET, queryset=queryset)
        return self.filterset.qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter'] = self.filterset
        return context


class BillCreateView(LoginRequiredMixin, CreateView):
    """View for creating a new bill."""
    model = Bill
    template_name = 'bills/billcreate.html'
    fields = [
        'institution_name',
        'phone_number',
        'email',
        'address',
        'description',
        'payment_details',
        'amount',
        'status'
    ]

    def get_success_url(self):
        """Redirect to the list of bills after a successful update."""
        return reverse('bill_list')


class BillUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    """View for updating an existing bill."""
    model = Bill
    template_name = 'bills/billupdate.html'
    fields = [
        'institution_name',
        'phone_number',
        'email',
        'address',
        'description',
        'payment_details',
        'amount',
        'status'
    ]

    def test_func(self):
        """Check if the user has the required permissions."""
        return self.request.user.profile in Profile.objects.all()

    def get_success_url(self):
        """Redirect to the list of bills after a successful update."""
        return reverse('bill_list')


class BillDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    """View for deleting a bill."""
    model = Bill
    template_name = 'bills/billdelete.html'

    def test_func(self):
        """Check if the user is a superuser."""
        return self.request.user.is_superuser

    def get_success_url(self):
        """Redirect to the list of bills after successful deletion."""
        return reverse('bill_list')
