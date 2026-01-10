"""
Module: admin.py

Django admin configurations for managing categories, items, and deliveries.

This module defines the following admin classes:
- CategoryAdmin: Configuration for the Category model in the admin interface.
- ItemAdmin: Configuration for the Item model in the admin interface.
- DeliveryAdmin: Configuration for the Delivery model in the admin interface.
"""

from django.contrib import admin
from .models import Category, Item, Delivery, ProductVariation


class CategoryAdmin(admin.ModelAdmin):
    """
    Admin configuration for the Category model.
    """
    list_display = ('name', 'slug')
    search_fields = ('name',)
    ordering = ('name',)


class ProductVariationInline(admin.TabularInline):
    """
    Inline admin for ProductVariation.
    """
    model = ProductVariation
    extra = 1
    fields = ('variation_type', 'name', 'value', 'quantity', 'price_adjustment', 'is_active')


class ItemAdmin(admin.ModelAdmin):
    """
    Admin configuration for the Item model.
    """
    list_display = (
        'name', 'category', 'quantity', 'price', 'expiring_date', 'vendor'
    )
    search_fields = ('name', 'category__name', 'vendor__name')
    list_filter = ('category', 'vendor')
    ordering = ('name',)
    inlines = [ProductVariationInline]


class ProductVariationAdmin(admin.ModelAdmin):
    """
    Admin configuration for the ProductVariation model.
    """
    list_display = (
        'item', 'variation_type', 'name', 'value', 'quantity', 
        'price_adjustment', 'is_active'
    )
    search_fields = ('item__name', 'name', 'value')
    list_filter = ('variation_type', 'is_active', 'item__category')
    ordering = ('item', 'variation_type', 'name')


class DeliveryAdmin(admin.ModelAdmin):
    """
    Admin configuration for the Delivery model.
    """
    list_display = (
        'item', 'customer_name', 'phone_number',
        'location', 'date', 'is_delivered'
    )
    search_fields = ('item__name', 'customer_name')
    list_filter = ('is_delivered', 'date')
    ordering = ('-date',)


admin.site.register(Category, CategoryAdmin)
admin.site.register(Item, ItemAdmin)
admin.site.register(Delivery, DeliveryAdmin)
admin.site.register(ProductVariation, ProductVariationAdmin)
