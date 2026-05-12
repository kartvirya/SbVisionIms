from django.db import models
from django_extensions.db.fields import AutoSlugField

from store.models import Item


class Invoice(models.Model):
    """
    Legacy standalone invoice (customer-facing totals only).

    Prefer ``transactions.Sale`` + inventory transactions for stock and ledger.
    Optionally link rows here for reference.

    Attributes:
        slug (str): Unique slug based on the date.
        date (datetime): Date of invoice creation.
        customer_name (str): Name of the customer.
        contact_number (str): Customer's contact number.
        item (ForeignKey): The invoiced item.
        price_per_item (float): Price per item.
        quantity (float): Number of items purchased.
        shipping (float): Shipping charges.
        total (float): Total before shipping.
        grand_total (float): Total including shipping.
    """

    slug = AutoSlugField(unique=True, populate_from='date')
    date = models.DateTimeField(
        auto_now=True,
        verbose_name='Date (e.g., 2022/11/22)'
    )
    customer_name = models.CharField(max_length=30)
    contact_number = models.CharField(max_length=13)
    item = models.ForeignKey(Item, on_delete=models.CASCADE)
    price_per_item = models.FloatField(verbose_name='Price Per Item (Rs)')
    quantity = models.FloatField(default=0.00)
    shipping = models.FloatField(verbose_name='Shipping and Handling')
    total = models.FloatField(
        verbose_name='Total Amount (Rs)', editable=False
    )
    grand_total = models.FloatField(
        verbose_name='Grand Total (Rs)', editable=False
    )
    linked_sale = models.ForeignKey(
        "transactions.Sale",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="standalone_invoices",
        help_text="Canonical sale in transactions app (recommended).",
    )
    linked_inventory_transaction = models.ForeignKey(
        "transactions.InventoryTransaction",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="legacy_invoice_documents",
        help_text="Optional link to unified inventory/accounting txn.",
    )

    def save(self, *args, **kwargs):
        """
        Update total and grand_total before saving.
        """
        self.total = round(self.quantity * self.price_per_item, 2)
        self.grand_total = round(self.total + self.shipping, 2)
        return super().save(*args, **kwargs)

    def __str__(self):
        """
        Return the invoice's slug.
        """
        return self.slug
