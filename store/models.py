"""
Module: models.py

Contains Django models for handling categories, items, and deliveries.

This module defines the following classes:
- Category: Represents a category for items.
- Item: Represents an item in the inventory.
- Delivery: Represents a delivery of an item to a customer.

Each class provides specific fields and methods for handling related data.
"""

from django.db import models
from django.urls import reverse
from django.forms import model_to_dict
from django_extensions.db.fields import AutoSlugField
from accounts.models import Vendor, Logistics
from imagekit.models import ProcessedImageField
from imagekit.processors import ResizeToFill
from django.utils import timezone


class Category(models.Model):
    """
    Represents a category for items.
    """
    name = models.CharField(max_length=50)
    slug = AutoSlugField(unique=True, populate_from='name')

    def __str__(self):
        """
        String representation of the category.
        """
        return f"Category: {self.name}"

    class Meta:
        verbose_name_plural = 'Categories'


class Item(models.Model):
    """
    Represents an item in the inventory.
    """
    slug = AutoSlugField(unique=True, populate_from='name')
    name = models.CharField(max_length=50)
    description = models.TextField(max_length=256)
    category = models.ForeignKey(Category, on_delete=models.CASCADE)
    quantity = models.IntegerField(default=0)
    price = models.FloatField(
        default=0,
        verbose_name='Selling Price',
        help_text='Price at which the product is sold to customers'
    )
    cost_price = models.FloatField(
        default=0.0,
        verbose_name='Cost Price',
        help_text='Cost price of the product (purchase price)'
    )
    low_stock_threshold = models.IntegerField(
        default=10,
        verbose_name='Low Stock Threshold',
        help_text='Alert when stock falls below this quantity'
    )
    expiring_date = models.DateTimeField(null=True, blank=True)
    vendor = models.ForeignKey(Vendor, on_delete=models.SET_NULL, null=True)
    image = ProcessedImageField(
        upload_to='products/',
        processors=[ResizeToFill(800, 800)],
        format='JPEG',
        options={'quality': 90},
        blank=True,
        null=True,
        help_text='Product image'
    )

    def __str__(self):
        """
        String representation of the item.
        """
        return (
            f"{self.name} - Category: {self.category}, "
            f"Quantity: {self.quantity}"
        )

    def get_absolute_url(self):
        """
        Returns the absolute URL for an item detail view.
        """
        return reverse('item-detail', kwargs={'slug': self.slug})

    def get_profit_margin(self):
        """
        Calculate profit margin percentage.
        """
        if self.cost_price > 0 and self.price > 0:
            return ((self.price - self.cost_price) / self.price) * 100
        return 0.0

    def get_profit_amount(self):
        """
        Calculate profit amount per unit.
        """
        return self.price - self.cost_price

    def get_current_stock(self):
        """On-hand quantity from stock movements (synced to quantity cache)."""
        from store.stock_utils import get_item_current_stock

        return get_item_current_stock(self)

    def is_low_stock(self):
        """True when on-hand stock is at or below the alert threshold."""
        return self.get_current_stock() <= self.low_stock_threshold

    def to_json(self):
        product = model_to_dict(self, exclude=['slug'])
        # Convert image field to URL string if it exists
        if self.image:
            product['image'] = self.image.url
        else:
            product['image'] = None
        # Convert datetime to string for JSON serialization
        if product.get('expiring_date'):
            expiring_date = product['expiring_date']
            if hasattr(expiring_date, 'isoformat'):
                product['expiring_date'] = expiring_date.isoformat()
            elif isinstance(expiring_date, str):
                pass  # Already a string
        # Include variations
        variations = []
        for variation in self.variations.filter(is_active=True):
            variations.append({
                'id': variation.id,
                'type': variation.variation_type,
                'type_display': variation.get_variation_type_display(),
                'name': variation.name,
                'value': variation.value or '',
                'quantity': variation.quantity,
                'price_adjustment': float(variation.price_adjustment),
                'final_price': float(variation.final_price),
            })
        product['variations'] = variations
        # Ensure all values are JSON-serializable
        product['id'] = self.id
        product['text'] = self.name
        product['category'] = self.category.name
        product['price'] = float(self.price or 0)
        on_hand = self.get_current_stock()
        product['stock'] = on_hand
        product['quantity'] = 1
        product['total_product'] = 0
        return product

    class Meta:
        ordering = ['name']
        verbose_name_plural = 'Items'


class ProductVariation(models.Model):
    """
    Represents variations of a product (color, size, etc.)
    """
    VARIATION_TYPES = [
        ('color', 'Color'),
        ('size', 'Size'),
        ('material', 'Material'),
        ('style', 'Style'),
        ('other', 'Other'),
    ]
    
    item = models.ForeignKey(
        Item, 
        related_name='variations',
        on_delete=models.CASCADE
    )
    variation_type = models.CharField(
        max_length=20,
        choices=VARIATION_TYPES,
        default='other'
    )
    name = models.CharField(
        max_length=50,
        help_text='e.g., Red, Large, Cotton, etc.'
    )
    value = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text='Optional: hex color code, dimensions, etc.'
    )
    quantity = models.IntegerField(
        default=0,
        help_text='Quantity available for this variation'
    )
    price_adjustment = models.FloatField(
        default=0.0,
        help_text='Price adjustment for this variation (+/-)'
    )
    is_active = models.BooleanField(
        default=True,
        help_text='Whether this variation is currently available'
    )
    
    def __str__(self):
        return f"{self.item.name} - {self.get_variation_type_display()}: {self.name}"
    
    @property
    def final_price(self):
        """Calculate the final price including adjustment"""
        return self.item.price + self.price_adjustment
    
    class Meta:
        ordering = ['variation_type', 'name']
        unique_together = ['item', 'variation_type', 'name']
        verbose_name_plural = 'Product Variations'


class Delivery(models.Model):
    """
    Represents a delivery of an item to a customer.
    """
    item = models.ForeignKey(
        Item, blank=True, null=True, on_delete=models.SET_NULL
    )
    customer_name = models.CharField(max_length=30, blank=True, null=True)
    phone_number = models.CharField(
        max_length=30,
        blank=True,
        null=True,
        verbose_name='Phone Number',
        help_text='Enter phone number (e.g., +977 98XXXXXXXX or 01-XXXXXXX)'
    )
    location = models.CharField(max_length=20, blank=True, null=True)
    date = models.DateTimeField()
    logistics = models.ForeignKey(
        Logistics,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        verbose_name='Logistics Company',
        help_text='Select the logistics company for this delivery'
    )
    tracking_number = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name='Tracking Number',
        help_text='Package tracking number'
    )
    is_delivered = models.BooleanField(
        default=False, verbose_name='Is Delivered'
    )

    def __str__(self):
        """
        String representation of the delivery.
        """
        return (
            f"Delivery of {self.item} to {self.customer_name} "
            f"at {self.location} on {self.date}"
        )
