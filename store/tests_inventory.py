from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings

from accounts.models import Vendor
from store.models import Category, Item, ProductVariation, StockAdjustmentLog
from store.views import _category_delete_blockers, _item_delete_blockers
from transactions.services import (
    ACCOUNT_BILL_ITEM_NAME,
    create_payable_quick_entry,
    get_account_bill_placeholder_item,
)


class InventoryVisibilityTests(TestCase):
    def setUp(self):
        self.vendor = Vendor.objects.create(name="Test Vendor")
        self.category = Category.objects.create(name="Real Category")
        self.product = Item.objects.create(
            name="Real Product",
            description="Sellable",
            category=self.category,
            vendor=self.vendor,
            quantity=5,
            price=10,
            cost_price=6,
        )

    def test_account_placeholder_hidden_from_inventory_queryset(self):
        placeholder = get_account_bill_placeholder_item()
        visible = list(Item.inventory_queryset().values_list("name", flat=True))
        self.assertIn("Real Product", visible)
        self.assertNotIn(placeholder.name, visible)

    def test_ensure_purchase_uses_single_placeholder(self):
        create_payable_quick_entry(
            self.vendor,
            bill_number="ACC-1",
            net_amount=Decimal("500"),
        )
        create_payable_quick_entry(
            self.vendor,
            bill_number="ACC-2",
            net_amount=Decimal("300"),
        )
        placeholders = Item.objects.filter(is_account_placeholder=True)
        self.assertEqual(placeholders.count(), 1)
        self.assertEqual(placeholders.first().name, ACCOUNT_BILL_ITEM_NAME)

    def test_category_delete_ignores_placeholder_products(self):
        get_account_bill_placeholder_item()
        account_category = Category.objects.filter(name="Account entries").first()
        self.assertIsNotNone(account_category)
        blockers = _category_delete_blockers(account_category)
        self.assertEqual(blockers, [])

    def test_placeholder_item_cannot_be_deleted_from_inventory(self):
        placeholder = get_account_bill_placeholder_item()
        self.assertEqual(
            _item_delete_blockers(placeholder),
            ["internal account-book placeholder"],
        )

    @override_settings(ALLOWED_HOSTS=["*"])
    def test_product_delete_view_removes_unused_product(self):
        user = get_user_model().objects.create_superuser(
            "delete-tester", "delete@example.com", "pass"
        )
        item = Item.objects.create(
            name="Delete View Product",
            description="x",
            category=self.category,
            vendor=self.vendor,
            quantity=2,
            price=10,
            cost_price=5,
        )
        ProductVariation.objects.create(
            item=item, variation_type="size", name="M", quantity=1
        )
        StockAdjustmentLog.objects.create(
            item=item,
            mode="add",
            quantity_delta=2,
            quantity_before=0,
            quantity_after=2,
        )
        client = Client()
        client.force_login(user)
        response = client.post(f"/product/{item.slug}/delete/")
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Item.objects.filter(pk=item.pk).exists())
