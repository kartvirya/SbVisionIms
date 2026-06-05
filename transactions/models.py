from decimal import Decimal

from django.db import models
from django.db.models import Sum
from django.core.exceptions import ValidationError
from django.utils import timezone
from django_extensions.db.fields import AutoSlugField

from store.models import Item
from accounts.models import Vendor, Customer

RECEIPT_STATUS_CHOICES = [("P", "Pending"), ("S", "Received")]


def _d(value):
    return Decimal(str(value or 0))
PAYMENT_STATUS_CHOICES = [
    ("U", "Unpaid"),
    ("T", "Partial"),
    ("D", "Paid"),
    ("X", "Overpaid"),
]


class Sale(models.Model):
    """
    Represents a sale transaction involving a customer.
    """

    date_added = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Sale Date"
    )
    customer = models.ForeignKey(
        Customer,
        on_delete=models.DO_NOTHING,
        db_column="customer"
    )
    sub_total = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0.0
    )
    grand_total = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0.0
    )
    tax_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0.0
    )
    tax_percentage = models.FloatField(default=0.0)
    amount_paid = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0.0
    )
    amount_change = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0.0
    )
    inventory_transaction = models.OneToOneField(
        "InventoryTransaction",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="legacy_sale",
    )

    class Meta:
        db_table = "sales"
        verbose_name = "Sale"
        verbose_name_plural = "Sales"

    def save(self, *args, **kwargs):
        """When CustomerPayment rows exist, amount_paid is derived from those rows."""
        if self.pk:
            qs = getattr(self, "customer_payments", None)
            if qs is not None and qs.exists():
                agg = qs.aggregate(s=Sum("amount"))
                self.amount_paid = _d(agg["s"])
        super().save(*args, **kwargs)

    def __str__(self):
        """
        Returns a string representation of the Sale instance.
        """
        return (
            f"Sale ID: {self.id} | "
            f"Grand Total: {self.grand_total} | "
            f"Date: {self.date_added}"
        )

    def sum_products(self):
        """
        Returns the total quantity of products in the sale.
        """
        return sum(detail.quantity for detail in self.saledetail_set.all())


class SaleDetail(models.Model):
    """
    Represents details of a specific sale, including item and quantity.
    """

    sale = models.ForeignKey(
        Sale,
        on_delete=models.CASCADE,
        db_column="sale",
        related_name="saledetail_set"
    )
    item = models.ForeignKey(
        Item,
        on_delete=models.DO_NOTHING,
        db_column="item"
    )
    variation = models.ForeignKey(
        "store.ProductVariation",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sale_details",
    )
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )
    quantity = models.PositiveIntegerField()
    total_detail = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        db_table = "sale_details"
        verbose_name = "Sale Detail"
        verbose_name_plural = "Sale Details"

    def __str__(self):
        """
        Returns a string representation of the SaleDetail instance.
        """
        return (
            f"Detail ID: {self.id} | "
            f"Sale ID: {self.sale.id} | "
            f"Quantity: {self.quantity}"
        )


class SaleReturn(models.Model):
    """Customer return against a sale."""

    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="returns")
    reason = models.CharField(max_length=255, blank=True)
    total_credit = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_by = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sale_returns",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Sale return #{self.pk} for sale {self.sale_id}"


class SaleReturnLine(models.Model):
    sale_return = models.ForeignKey(
        SaleReturn, on_delete=models.CASCADE, related_name="lines"
    )
    sale_detail = models.ForeignKey(
        SaleDetail, on_delete=models.CASCADE, related_name="return_lines"
    )
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    line_credit = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    def __str__(self):
        return f"{self.quantity} × detail {self.sale_detail_id}"


class Purchase(models.Model):
    """
    Purchase order / bill header. Line items live on PurchaseLine; legacy item/qty/price
    columns remain for migrated rows until fully served by lines only.
    """

    slug = AutoSlugField(unique=True, populate_from="vendor")
    item = models.ForeignKey(
        Item,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text="Deprecated: use Purchase lines.",
    )
    description = models.TextField(max_length=300, blank=True, null=True)
    bill_number = models.CharField(
        max_length=64,
        blank=True,
        verbose_name="Bill number",
        help_text="Supplier invoice or bill reference number.",
    )
    vendor = models.ForeignKey(
        Vendor, related_name="purchases", on_delete=models.CASCADE
    )
    order_date = models.DateTimeField(default=timezone.now, verbose_name="Billed date")
    receipt_date = models.DateTimeField(
        blank=True, null=True, verbose_name="Receipt Date"
    )
    quantity = models.PositiveIntegerField(default=0)
    receipt_status = models.CharField(
        choices=RECEIPT_STATUS_CHOICES,
        max_length=1,
        default="P",
        verbose_name="Receipt Status",
    )
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0.0,
        verbose_name="Price per item (Rs)",
    )
    sub_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    vat_percentage = models.FloatField(default=0.0)
    vat_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    net_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    amount_remaining = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    payment_status = models.CharField(
        max_length=1,
        choices=PAYMENT_STATUS_CHOICES,
        default="U",
    )
    total_value = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    inventory_transaction = models.OneToOneField(
        "InventoryTransaction",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="legacy_purchase",
    )

    @property
    def total_line_quantity(self):
        if self.pk and self.lines.exists():
            agg = self.lines.aggregate(s=Sum("quantity"))
            return int(agg["s"] or 0)
        return int(self.quantity or 0)

    @property
    def display_bill_number(self):
        number = (self.bill_number or "").strip()
        if number:
            return number
        if self.pk:
            return f"PUR-{self.pk}"
        return "—"

    def save(self, *args, **kwargs):
        """
        Calculates the total value before saving the Purchase instance.
        """
        unit_price = Decimal(str(self.price or 0))
        quantity = Decimal(str(self.quantity or 0))
        discount_amount = Decimal(str(self.discount_amount or 0))
        amount_paid = Decimal(str(self.amount_paid or 0))
        if self.pk and self.vendor_payments.exists():
            agg = self.vendor_payments.aggregate(s=Sum("amount"))
            amount_paid = _d(agg["s"])
        vat_amount = Decimal(str(self.vat_amount or 0))

        if self.pk and self.lines.exists():
            agg = self.lines.aggregate(total=Sum("line_total"))
            line_sub = agg["total"] or Decimal("0")
            self.sub_total = line_sub
        else:
            self.sub_total = unit_price * quantity
        taxable_amount = self.sub_total - discount_amount
        if taxable_amount < 0:
            taxable_amount = 0

        vat_percentage = Decimal(str(self.vat_percentage or 0))
        if vat_percentage > 0:
            self.vat_amount = taxable_amount * (vat_percentage / Decimal("100"))
        else:
            self.vat_amount = vat_amount

        self.net_amount = taxable_amount + self.vat_amount
        self.amount_paid = amount_paid
        if self.amount_paid < 0:
            raise ValidationError("Amount paid cannot be negative.")

        self.amount_remaining = self.net_amount - self.amount_paid
        if self.amount_paid == 0:
            self.payment_status = "U"
        elif self.amount_remaining > 0:
            self.payment_status = "T"
        elif self.amount_remaining == 0:
            self.payment_status = "D"
        else:
            self.payment_status = "X"
        self.total_value = self.net_amount
        super().save(*args, **kwargs)

    def __str__(self):
        """
        Returns a string representation of the Purchase instance.
        """
        if self.item_id:
            return str(self.item.name)
        first = self.lines.select_related("item").first()
        return first.item.name if first else f"Purchase #{self.pk}"

    class Meta:
        ordering = ["-order_date", "-id"]


class PurchaseLine(models.Model):
    """One line item on a multi-SKU purchase (order/receipt bill)."""

    purchase = models.ForeignKey(
        Purchase,
        on_delete=models.CASCADE,
        related_name="lines",
    )
    item = models.ForeignKey(Item, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    line_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        ordering = ["id"]

    def save(self, *args, **kwargs):
        qty = Decimal(str(self.quantity or 0))
        up = Decimal(str(self.unit_price or 0))
        self.line_total = qty * up
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.purchase_id} — {self.item.name}"


class PurchaseReturn(models.Model):
    """Supplier return against a purchase bill."""

    purchase = models.ForeignKey(
        Purchase,
        on_delete=models.CASCADE,
        related_name="returns",
    )
    reason = models.CharField(max_length=255, blank=True)
    total_credit = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_by = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="purchase_returns",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Return #{self.pk} for {self.purchase_id}"


class PurchaseReturnLine(models.Model):
    purchase_return = models.ForeignKey(
        PurchaseReturn,
        on_delete=models.CASCADE,
        related_name="lines",
    )
    purchase_line = models.ForeignKey(
        PurchaseLine,
        on_delete=models.CASCADE,
        related_name="return_lines",
    )
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    line_credit = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    def __str__(self):
        return f"{self.quantity} × {self.purchase_line_id}"


PAYMENT_METHOD_CHOICES = [
    ("cash", "Cash"),
    ("bank", "Bank transfer"),
]


class VendorPayment(models.Model):
    """Records a supplier payment affecting AP and optionally cash/bank ledger."""

    purchase = models.ForeignKey(
        Purchase,
        on_delete=models.CASCADE,
        related_name="vendor_payments",
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    paid_at = models.DateTimeField(auto_now_add=True)
    method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, default="cash")
    notes = models.TextField(blank=True)
    inventory_transaction = models.OneToOneField(
        "InventoryTransaction",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="vendor_payment",
    )

    class Meta:
        ordering = ["-paid_at"]

    def __str__(self):
        return f"Vendor payment #{self.pk} ({self.amount})"


class CustomerPayment(models.Model):
    """Records customer receipt against AR with optional cash/bank ledger."""

    sale = models.ForeignKey(
        "Sale",
        on_delete=models.CASCADE,
        related_name="customer_payments",
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    received_at = models.DateTimeField(auto_now_add=True)
    method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, default="cash")
    notes = models.TextField(blank=True)
    inventory_transaction = models.OneToOneField(
        "InventoryTransaction",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="customer_payment",
    )

    class Meta:
        ordering = ["-received_at"]

    def __str__(self):
        return f"Customer payment #{self.pk} ({self.amount})"


class InventoryTransaction(models.Model):
    """Unified transaction header for inventory and accounting events."""

    class TransactionType(models.TextChoices):
        PURCHASE = "purchase", "Purchase"
        SALE = "sale", "Sale"
        RETURN = "return", "Return"
        ADJUSTMENT = "adjustment", "Adjustment"
        PAYMENT = "payment", "Payment"

    class TransactionStatus(models.TextChoices):
        DRAFT = "draft", "Draft"
        POSTED = "posted", "Posted"
        CANCELLED = "cancelled", "Cancelled"

    date = models.DateTimeField(auto_now_add=True)
    transaction_type = models.CharField(max_length=20, choices=TransactionType.choices)
    status = models.CharField(
        max_length=20,
        choices=TransactionStatus.choices,
        default=TransactionStatus.POSTED,
    )
    vendor = models.ForeignKey(
        Vendor,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inventory_transactions",
    )
    customer = models.ForeignKey(
        Customer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inventory_transactions",
    )
    notes = models.TextField(blank=True, null=True)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    source_ref = models.CharField(max_length=100, null=True, blank=True, unique=True)

    class Meta:
        db_table = "inventory_transactions"
        ordering = ["-date", "-id"]

    def __str__(self):
        return f"{self.transaction_type} #{self.id}"


class InventoryTransactionItem(models.Model):
    """Line items for the unified inventory transaction."""

    transaction = models.ForeignKey(
        InventoryTransaction,
        on_delete=models.CASCADE,
        related_name="items",
    )
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="transaction_items")
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    line_total = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        db_table = "inventory_transaction_items"
        constraints = [
            models.CheckConstraint(
                check=models.Q(quantity__gt=0),
                name="inv_txn_item_quantity_gt_zero",
            ),
            models.CheckConstraint(
                check=models.Q(unit_price__gte=0),
                name="inv_txn_item_unit_price_gte_zero",
            ),
            models.CheckConstraint(
                check=models.Q(line_total__gte=0),
                name="inv_txn_item_line_total_gte_zero",
            ),
        ]

    def __str__(self):
        return f"{self.transaction_id} - {self.item.name}"


class StockMovement(models.Model):
    """Append-only stock movement log used to compute current stock."""

    class MovementType(models.TextChoices):
        IN = "IN", "Stock In"
        OUT = "OUT", "Stock Out"

    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="stock_movements")
    transaction = models.ForeignKey(
        InventoryTransaction,
        on_delete=models.CASCADE,
        related_name="stock_movements",
    )
    movement_type = models.CharField(max_length=3, choices=MovementType.choices)
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "stock_movements"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["item", "movement_type"]),
            models.Index(fields=["transaction"]),
            models.Index(fields=["item", "created_at"]),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(quantity__gt=0),
                name="stock_move_quantity_gt_zero",
            ),
        ]

    def __str__(self):
        return f"{self.item_id} {self.movement_type} {self.quantity}"


class LedgerEntry(models.Model):
    """Double-entry accounting rows generated from inventory transactions."""

    transaction = models.ForeignKey(
        InventoryTransaction,
        on_delete=models.CASCADE,
        related_name="ledger_entries",
    )
    account = models.CharField(max_length=100)
    debit = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    credit = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ledger_entries"
        ordering = ["id"]
        indexes = [models.Index(fields=["transaction", "account"])]

    def __str__(self):
        return f"{self.transaction_id} {self.account}"
