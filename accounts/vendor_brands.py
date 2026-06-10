"""Shared supplier brand add/remove handling."""

from django.contrib import messages
from django.db import IntegrityError

from .forms import VendorBrandForm
from .models import Brand


def handle_vendor_brand_action(request, vendor):
    """
    Process add_brand / delete_brand POST actions for a vendor.
    Returns True if the action was handled, False otherwise.
    """
    action = request.POST.get("action")
    if action == "add_brand":
        form = VendorBrandForm(request.POST)
        if form.is_valid():
            brand = form.save(commit=False)
            brand.vendor = vendor
            try:
                brand.save()
                messages.success(
                    request,
                    f'Brand "{brand.name}" added to {vendor.name}.',
                )
            except IntegrityError:
                messages.error(
                    request,
                    f'Brand "{brand.name}" already exists for {vendor.name}.',
                )
        else:
            messages.error(request, "Enter a valid brand name.")
        return True

    if action == "update_brand":
        brand = Brand.objects.filter(
            pk=request.POST.get("brand_id"),
            vendor=vendor,
        ).first()
        if not brand:
            messages.error(request, "Brand not found.")
            return True
        form = VendorBrandForm(request.POST, instance=brand)
        if form.is_valid():
            try:
                updated = form.save()
                messages.success(
                    request,
                    f'Brand "{updated.name}" updated.',
                )
            except IntegrityError:
                messages.error(
                    request,
                    f'Brand "{form.cleaned_data.get("name")}" already exists for {vendor.name}.',
                )
        else:
            messages.error(request, "Enter a valid brand name.")
        return True

    if action == "delete_brand":
        brand = Brand.objects.filter(
            pk=request.POST.get("brand_id"),
            vendor=vendor,
        ).first()
        if brand:
            name = brand.name
            brand.delete()
            messages.success(request, f'Brand "{name}" removed.')
        else:
            messages.error(request, "Brand not found.")
        return True

    return False
