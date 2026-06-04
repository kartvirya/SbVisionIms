from decimal import Decimal

from django.test import TestCase

from accounts.models import Customer, Vendor
from store.models import Category, Item
from transactions.models import InventoryTransaction, LedgerEntry, Purchase, VendorPayment
from store.models import ProductVariation
from store.stock_utils import get_ledger_stock, get_sellable_stock
from transactions.forms import PurchaseForm
from transactions.services import (
    create_payable_quick_entry,
    create_sale_transaction,
    get_payables_aging,
    get_payables_aging_report,
    post_vendor_payment_ledger,
    reconcile_ledger_stock_to_target,
    sync_purchase_inventory_transaction,
    update_vendor_payables_adjustment,
)


class PurchaseInventorySyncTests(TestCase):
    def setUp(self):
        self.vendor = Vendor.objects.create(name="Vendor A")
        self.category = Category.objects.create(name="General")
        self.item = Item.objects.create(
            name="Item A",
            description="Test",
            category=self.category,
            quantity=0,
            price=20,
            cost_price=10,
            vendor=self.vendor,
        )

    def _create_purchase(self, receipt_status="S", amount_paid=0):
        return Purchase.objects.create(
            item=self.item,
            vendor=self.vendor,
            quantity=5,
            price=10,
            receipt_status=receipt_status,
            discount_amount=0,
            vat_percentage=0,
            amount_paid=amount_paid,
        )

    def test_purchase_sync_is_idempotent(self):
        purchase = self._create_purchase()

        first_txn = sync_purchase_inventory_transaction(purchase=purchase)
        second_txn = sync_purchase_inventory_transaction(purchase=purchase)

        self.assertIsNotNone(first_txn)
        self.assertEqual(first_txn.id, second_txn.id)
        self.assertEqual(
            InventoryTransaction.objects.filter(source_ref=f"purchase:{purchase.id}").count(),
            1,
        )

    def test_receipt_pending_does_not_post_inventory(self):
        purchase = self._create_purchase(receipt_status="P")
        self.assertIsNone(sync_purchase_inventory_transaction(purchase=purchase))
        self.assertFalse(
            InventoryTransaction.objects.filter(source_ref=f"purchase:{purchase.id}").exists()
        )

    def test_payment_status_updates_from_amounts(self):
        unpaid = self._create_purchase(amount_paid=0)
        self.assertEqual(unpaid.payment_status, "U")

        partial = self._create_purchase(amount_paid=20)
        self.assertEqual(partial.payment_status, "T")

        full = self._create_purchase(amount_paid=50)
        self.assertEqual(full.payment_status, "D")

    def test_payables_aging_returns_vendor_totals(self):
        self._create_purchase(amount_paid=10)
        self.item.quantity = 12
        self.item.cost_price = 10
        self.item.save(update_fields=["quantity", "cost_price"])

        rows = list(get_payables_aging())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].id, self.vendor.id)
        self.assertEqual(Decimal(rows[0].total_outstanding), Decimal("40"))
        self.assertEqual(int(rows[0].total_stock), 12)
        self.assertEqual(Decimal(rows[0].total_stock_value), Decimal("120"))
        self.assertIsNotNone(rows[0].last_transaction_date)
        self.assertEqual(Decimal(rows[0].balance_due), Decimal("40"))

    def test_payables_adjustment_updates_balance_due(self):
        self._create_purchase(amount_paid=10)
        update_vendor_payables_adjustment(self.vendor.id, "5", sign="-")
        row = get_payables_aging().get(pk=self.vendor.id)
        self.assertEqual(Decimal(row.payables_adjustment), Decimal("-5"))
        self.assertEqual(Decimal(row.balance_due), Decimal("35"))

    def test_payables_aging_report_includes_bill_and_dates(self):
        purchase = self._create_purchase(amount_paid=10)
        purchase.bill_number = "INV-1001"
        purchase.save(update_fields=["bill_number"])
        groups = get_payables_aging_report()
        self.assertEqual(len(groups), 1)
        bill = groups[0]["bills"][0]
        self.assertEqual(bill["bill_number"], "INV-1001")
        self.assertIsNotNone(bill["billed_date"])
        self.assertIsNotNone(bill["last_transaction_date"])


class PaymentAndCogsTests(TestCase):
    def setUp(self):
        self.vendor = Vendor.objects.create(name="Vendor B")
        self.category = Category.objects.create(name="General")
        self.item = Item.objects.create(
            name="Widget",
            description="Test",
            category=self.category,
            quantity=0,
            price=50,
            cost_price=1,
            vendor=self.vendor,
        )
        self.customer = Customer.objects.create(first_name="Sam", last_name="C", phone="555")

    def test_vendor_payment_posts_cash_ledger(self):
        purchase = Purchase.objects.create(
            item=self.item,
            vendor=self.vendor,
            quantity=5,
            price=10,
            receipt_status="S",
            discount_amount=0,
            vat_percentage=0,
            amount_paid=0,
        )
        sync_purchase_inventory_transaction(purchase=purchase)
        VendorPayment.objects.create(purchase=purchase, amount=Decimal("25"), method="cash")
        self.assertTrue(
            LedgerEntry.objects.filter(
                account="Cash",
                credit=Decimal("25"),
            ).exists()
        )

    def test_sale_adds_cogs_and_inventory_ledger(self):
        purchase = Purchase.objects.create(
            item=self.item,
            vendor=self.vendor,
            quantity=5,
            price=10,
            receipt_status="S",
            discount_amount=0,
            vat_percentage=0,
            amount_paid=0,
        )
        sync_purchase_inventory_transaction(purchase=purchase)
        create_sale_transaction(
            customer=self.customer,
            items=[
                {
                    "item": self.item.pk,
                    "quantity": 2,
                    "unit_price": Decimal("30"),
                }
            ],
            notes="Test sale",
        )
        self.assertTrue(
            LedgerEntry.objects.filter(
                account="Cost of Goods Sold",
                debit=Decimal("20"),
            ).exists()
        )
        self.assertTrue(
            LedgerEntry.objects.filter(
                account="Inventory",
                credit=Decimal("20"),
            ).exists()
        )


class StockAndPayablesFixTests(TestCase):
    def setUp(self):
        self.vendor = Vendor.objects.create(name="Vendor C")
        self.category = Category.objects.create(name="General")
        self.item = Item.objects.create(
            name="Variant Shirt",
            description="Test",
            category=self.category,
            quantity=0,
            price=100,
            cost_price=40,
            vendor=self.vendor,
        )
        self.customer = Customer.objects.create(first_name="Alex", last_name=None)
        self.variation = ProductVariation.objects.create(
            item=self.item,
            variation_type="size",
            name="M",
            quantity=5,
            is_active=True,
        )
        purchase = Purchase.objects.create(
            item=self.item,
            vendor=self.vendor,
            quantity=10,
            price=10,
            receipt_status="S",
            discount_amount=0,
            vat_percentage=0,
            amount_paid=0,
        )
        sync_purchase_inventory_transaction(purchase=purchase)

    def test_customer_name_without_last_name(self):
        self.assertEqual(str(self.customer), "Alex")
        self.assertEqual(self.customer.get_full_name(), "Alex")

    def test_receipt_date_sets_received_status(self):
        from django.utils import timezone

        form = PurchaseForm(
            data={
                "vendor": self.vendor.pk,
                "order_date": timezone.localtime().strftime("%Y-%m-%dT%H:%M"),
                "receipt_status": "P",
                "receipt_date": timezone.localtime().strftime("%Y-%m-%dT%H:%M"),
                "discount_amount": "0",
                "vat_percentage": "13",
                "vat_amount": "0",
                "amount_paid": "0",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["receipt_status"], "S")

    def test_reconcile_ledger_adjustment_is_idempotent(self):
        reconcile_ledger_stock_to_target(self.item, 7, notes="first")
        reconcile_ledger_stock_to_target(self.item, 9, notes="second")
        self.assertEqual(get_ledger_stock(self.item), 9)
        self.assertEqual(
            InventoryTransaction.objects.filter(
                source_ref=f"adjustment:item:{self.item.id}"
            ).count(),
            1,
        )

    def test_variant_sale_deducts_variant_not_ledger(self):
        ledger_before = get_ledger_stock(self.item)
        create_sale_transaction(
            customer=self.customer,
            items=[
                {
                    "item": self.item.pk,
                    "quantity": 2,
                    "unit_price": Decimal("120"),
                    "variation_id": self.variation.pk,
                }
            ],
        )
        self.variation.refresh_from_db()
        self.assertEqual(self.variation.quantity, 3)
        self.assertEqual(get_ledger_stock(self.item), ledger_before)
        self.assertEqual(get_sellable_stock(self.item), ledger_before)

    def test_base_sale_uses_ledger_not_variant_pool(self):
        self.assertEqual(get_sellable_stock(self.item), get_ledger_stock(self.item))

    def test_payable_quick_entry_creates_vendor_payment(self):
        purchase = create_payable_quick_entry(
            self.vendor,
            bill_number="QB-1",
            net_amount=Decimal("500"),
            amount_paid=Decimal("100"),
        )
        self.assertEqual(purchase.vendor_payments.count(), 1)
        self.assertEqual(purchase.amount_paid, Decimal("100"))
        payment = purchase.vendor_payments.first()
        self.assertTrue(
            LedgerEntry.objects.filter(
                account="Cash",
                credit=Decimal("100"),
            ).exists()
        )
        post_vendor_payment_ledger(payment=payment)
        payment.amount = Decimal("150")
        payment.save()
        post_vendor_payment_ledger(payment=payment)
        self.assertEqual(
            LedgerEntry.objects.filter(
                account="Cash",
                credit=Decimal("150"),
            ).count(),
            1,
        )
