from django.db import models
from django.contrib.auth.models import User

from django_extensions.db.fields import AutoSlugField
from imagekit.models import ProcessedImageField
from imagekit.processors import ResizeToFill
from phonenumber_field.modelfields import PhoneNumberField


# Define choices for profile status and roles
STATUS_CHOICES = [
    ('INA', 'Inactive'),
    ('A', 'Active'),
    ('OL', 'On leave')
]

ROLE_CHOICES = [
    ('OP', 'Operative'),
    ('EX', 'Executive'),
    ('AD', 'Admin')
]


class Profile(models.Model):
    """
    Represents a user profile containing personal and account-related details.
    """
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, verbose_name='User'
    )
    slug = AutoSlugField(
        unique=True,
        verbose_name='Account ID',
        populate_from='email'
    )
    profile_picture = ProcessedImageField(
        default='profile_pics/default.jpg',
        upload_to='profile_pics',
        format='JPEG',
        processors=[ResizeToFill(150, 150)],
        options={'quality': 100}
    )
    telephone = PhoneNumberField(
        null=True, blank=True, verbose_name='Telephone'
    )
    email = models.EmailField(
        max_length=150, blank=True, null=True, verbose_name='Email'
    )
    first_name = models.CharField(
        max_length=30, blank=True, verbose_name='First Name'
    )
    last_name = models.CharField(
        max_length=30, blank=True, verbose_name='Last Name'
    )
    status = models.CharField(
        choices=STATUS_CHOICES,
        max_length=12,
        default='INA',
        verbose_name='Status'
    )
    role = models.CharField(
        choices=ROLE_CHOICES,
        max_length=12,
        blank=True,
        null=True,
        verbose_name='Role'
    )

    @property
    def image_url(self):
        """
        Returns the URL of the profile picture.
        Returns an empty string if the image is not available.
        """
        try:
            return self.profile_picture.url
        except AttributeError:
            return ''

    def __str__(self):
        """
        Returns a string representation of the profile.
        """
        return f"{self.user.username} Profile"

    class Meta:
        """Meta options for the Profile model."""
        ordering = ['slug']
        verbose_name = 'Profile'
        verbose_name_plural = 'Profiles'


class Vendor(models.Model):
    """
    Represents a vendor with contact and address information.
    """
    name = models.CharField(max_length=50, verbose_name='Name')
    slug = AutoSlugField(
        unique=True,
        populate_from='name',
        verbose_name='Slug'
    )
    phone_number = models.BigIntegerField(
        blank=True, null=True, verbose_name='Phone Number'
    )
    address = models.CharField(
        max_length=50, blank=True, null=True, verbose_name='Address'
    )
    payables_adjustment = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name='Payables adjustment',
        help_text='Manual adjustment (+/-) applied on the payables aging report.',
    )
    opening_balance = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        help_text="Amount owed to this supplier before system records.",
    )

    def __str__(self):
        """
        Returns a string representation of the vendor.
        """
        return self.name

    class Meta:
        """Meta options for the Vendor model."""
        verbose_name = 'Vendor'
        verbose_name_plural = 'Vendors'


class Customer(models.Model):
    first_name = models.CharField(max_length=256)
    last_name = models.CharField(max_length=256, blank=True, null=True)
    address = models.TextField(max_length=256, blank=True, null=True)
    email = models.EmailField(max_length=256, blank=True, null=True)
    phone = models.CharField(max_length=30, blank=True, null=True)
    loyalty_points = models.IntegerField(default=0)
    opening_balance = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        help_text="Amount the customer owed before system records (debit balance).",
    )

    class Meta:
        db_table = 'Customers'

    def get_full_name(self):
        last = (self.last_name or "").strip()
        if last:
            return f"{self.first_name} {last}"
        return self.first_name

    def __str__(self) -> str:
        return self.get_full_name()

    def to_select2(self):
        item = {
            "label": self.get_full_name(),
            "value": self.id
        }
        return item


class Logistics(models.Model):
    """
    Represents a logistics/shipping company for package deliveries.
    """
    name = models.CharField(
        max_length=100,
        verbose_name='Logistics Company Name'
    )
    slug = AutoSlugField(
        unique=True,
        populate_from='name',
        verbose_name='Slug'
    )
    contact_person = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name='Contact Person'
    )
    phone_number = models.CharField(
        max_length=30,
        blank=True,
        null=True,
        verbose_name='Phone Number',
        help_text='Enter phone number (e.g., +977 98XXXXXXXX or 01-XXXXXXX)'
    )
    email = models.EmailField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name='Email Address'
    )
    address = models.TextField(
        max_length=500,
        blank=True,
        null=True,
        verbose_name='Address'
    )
    tracking_url = models.URLField(
        max_length=500,
        blank=True,
        null=True,
        verbose_name='Tracking URL Template',
        help_text='URL template for tracking (use {tracking_number} as placeholder)'
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name='Active',
        help_text='Whether this logistics company is currently active'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Created At'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Updated At'
    )

    class Meta:
        verbose_name = 'Logistics Company'
        verbose_name_plural = 'Logistics Companies'
        ordering = ['name']

    def __str__(self):
        return self.name


class Company(models.Model):
    """
    Represents company information for invoices, bills, and receipts.
    Uses singleton pattern - only one company record should exist.
    """
    name = models.CharField(
        max_length=100,
        default='SB Vision',
        verbose_name='Company Name'
    )
    address = models.CharField(
        max_length=255,
        default='Tom Mboya Street, Tudor',
        blank=True,
        null=True,
        verbose_name='Street Address'
    )
    phone = models.CharField(
        max_length=30,
        default='+2547 00 000000',
        blank=True,
        null=True,
        verbose_name='Phone Number'
    )
    po_box = models.CharField(
        max_length=100,
        default='P.O BOX. 90420-80100 MSA',
        blank=True,
        null=True,
        verbose_name='P.O Box'
    )
    email = models.EmailField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name='Email Address'
    )
    website = models.URLField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name='Website'
    )

    class Meta:
        verbose_name = 'Company'
        verbose_name_plural = 'Company Information'
        ordering = ['id']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        """
        Override save to ensure only one company record exists.
        """
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        """
        Get or create the company instance (singleton pattern).
        """
        obj, created = cls.objects.get_or_create(pk=1)
        return obj
