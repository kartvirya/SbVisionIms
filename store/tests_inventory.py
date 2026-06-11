from decimal import Decimal

from django.test import TestCase

from accounts.models import Vendor
from store.models import Category, Item
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
