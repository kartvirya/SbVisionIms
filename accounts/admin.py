from django.contrib import admin
from .models import Profile, Vendor, Company, Logistics


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    """Admin interface for the Profile model."""
    list_display = ('user', 'telephone', 'email', 'role', 'status')


@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    """Admin interface for the Vendor model."""
    fields = ('name', 'phone_number', 'address')
    list_display = ('name', 'phone_number', 'address')
    search_fields = ('name', 'phone_number', 'address')


@admin.register(Logistics)
class LogisticsAdmin(admin.ModelAdmin):
    """Admin interface for the Logistics model."""
    list_display = ('name', 'contact_person', 'phone_number', 'email', 'is_active')
    list_filter = ('is_active', 'created_at')
    search_fields = ('name', 'contact_person', 'email', 'phone_number')
    fieldsets = (
        ('Company Information', {
            'fields': ('name', 'contact_person', 'phone_number', 'email', 'address')
        }),
        ('Tracking', {
            'fields': ('tracking_url',)
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
    )


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    """Admin interface for the Company model."""
    
    def has_add_permission(self, request):
        """Prevent adding multiple company records."""
        return not Company.objects.exists()
    
    def has_delete_permission(self, request, obj=None):
        """Prevent deleting the company record."""
        return False
    
    def has_change_permission(self, request, obj=None):
        """Allow changing the company record."""
        return True
    
    fieldsets = (
        ('Company Information', {
            'fields': ('name', 'address', 'phone', 'po_box', 'email', 'website')
        }),
    )
    
    list_display = ('name', 'address', 'phone', 'po_box')
    
    def changelist_view(self, request, extra_context=None):
        """Redirect to the edit page if company exists."""
        from django.shortcuts import redirect
        from django.urls import reverse
        company = Company.load()
        if company.pk:
            return redirect(reverse('admin:accounts_company_change', args=[company.pk]))
        return super().changelist_view(request, extra_context)
