from django.db import models
from autoslug import AutoSlugField


class Bill(models.Model):
    """
    Legacy vendor bill stub.

    Prefer ``transactions.Purchase`` for AP and inventory. Link optionally for auditing.
    """

    slug = AutoSlugField(unique=True, populate_from='date')
    date = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Date (e.g., 2022/11/22)'
    )
    institution_name = models.CharField(
        max_length=30,
        blank=False,
        null=False
    )
    phone_number = models.CharField(
        max_length=30,
        blank=True,
        null=True,
        help_text='Phone number of the institution'
    )
    email = models.EmailField(
        blank=True,
        null=True,
        help_text='Email address of the institution'
    )
    address = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text='Address of the institution'
    )
    description = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text='Description of the bill'
    )
    payment_details = models.CharField(
        max_length=255,
        blank=False,
        null=False,
        help_text='Details of the payment'
    )
    amount = models.FloatField(
        verbose_name='Total Amount Owing (Rs)',
        help_text='Total amount due for payment'
    )
    status = models.BooleanField(
        default=False,
        verbose_name='Paid',
        help_text='Payment status of the bill'
    )
    linked_purchase = models.ForeignKey(
        "transactions.Purchase",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="standalone_bills",
        help_text="Canonical purchase in transactions app.",
    )
    linked_inventory_transaction = models.ForeignKey(
        "transactions.InventoryTransaction",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="legacy_bill_documents",
    )

    def __str__(self):
        return self.institution_name
