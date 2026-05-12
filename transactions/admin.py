from django.contrib import admin

from .models import (
    CustomerPayment,
    Purchase,
    PurchaseLine,
    Sale,
    SaleDetail,
    VendorPayment,
)


class PurchaseLineInline(admin.TabularInline):
    model = PurchaseLine
    extra = 0


class VendorPaymentInline(admin.TabularInline):
    model = VendorPayment
    extra = 0
    readonly_fields = ("inventory_transaction", "paid_at")


class CustomerPaymentInline(admin.TabularInline):
    model = CustomerPayment
    extra = 0
    readonly_fields = ("inventory_transaction", "received_at")


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "customer",
        "date_added",
        "grand_total",
        "amount_paid",
        "amount_change",
    )
    search_fields = ("customer__name", "id")
    list_filter = ("date_added", "customer")
    ordering = ("-date_added",)
    readonly_fields = ("date_added",)
    date_hierarchy = "date_added"
    inlines = [CustomerPaymentInline]


@admin.register(SaleDetail)
class SaleDetailAdmin(admin.ModelAdmin):
    list_display = ("id", "sale", "item", "price", "quantity", "total_detail")
    search_fields = ("sale__id", "item__name")
    list_filter = ("sale", "item")
    ordering = ("sale", "item")


@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    list_display = (
        "slug",
        "vendor",
        "order_date",
        "receipt_date",
        "total_value",
        "receipt_status",
    )
    search_fields = ("vendor__name", "slug", "lines__item__name")
    list_filter = ("order_date", "vendor", "receipt_status")
    ordering = ("-order_date",)
    readonly_fields = ("total_value",)
    inlines = [PurchaseLineInline, VendorPaymentInline]


@admin.register(VendorPayment)
class VendorPaymentAdmin(admin.ModelAdmin):
    list_display = ("id", "purchase", "amount", "method", "paid_at")
    list_filter = ("method",)
    search_fields = ("purchase__id", "notes")


@admin.register(CustomerPayment)
class CustomerPaymentAdmin(admin.ModelAdmin):
    list_display = ("id", "sale", "amount", "method", "received_at")
    list_filter = ("method",)
    search_fields = ("sale__id", "notes")
