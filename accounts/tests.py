from decimal import Decimal

from django.contrib.auth import get_user_model
from django.http import QueryDict
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.account_dates import save_all_ledger_dates, save_bulk_purchase_dates
from accounts.contact_ledger import get_customer_ledger_rows, get_vendor_ledger_rows
from accounts.forms import CustomerAccountTransactionForm, VendorAccountTransactionForm
from accounts.models import Customer, Vendor
from transactions.models import CustomerPayment, Purchase, Sale, VendorPayment
from transactions.services import create_payable_quick_entry, create_receivable_quick_entry


class AccountTransactionTests(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create(first_name="Ram", last_name="Shrestha")
        self.vendor = Vendor.objects.create(name="Anyone Traders")
        user_model = get_user_model()
        self.user = user_model.objects.create_user("account_tester", password="secret")
        self.client = Client()
        self.client.force_login(self.user)

    def test_customer_sale_in_appears_in_ledger(self):
        sale = create_receivable_quick_entry(
            self.customer,
            reference="INV-1",
            amount=Decimal("1500"),
            sale_date=timezone.now(),
        )
        rows, balance = get_customer_ledger_rows(self.customer)
        self.assertEqual(balance, Decimal("1500"))
        self.assertTrue(any(row["type"] == "Sale" and row["debit"] == Decimal("1500") for row in rows))
        self.assertEqual(sale.grand_total, Decimal("1500"))

    def test_customer_account_transaction_post(self):
        url = reverse("customer-detail", args=[self.customer.pk])
        txn_date = timezone.localtime().replace(
            year=2026, month=6, day=1, hour=10, minute=0, second=0, microsecond=0
        )
        response = self.client.post(
            url,
            {
                "action": "account_transaction",
                "transaction_type": "sale_in",
                "amount": "2500",
                "reference": "SI-100",
                "method": "cash",
                "notes": "Account entry",
                "transaction_date": txn_date.strftime("%Y-%m-%dT%H:%M"),
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Sale.objects.filter(customer=self.customer).count(), 1)
        sale = Sale.objects.get(customer=self.customer)
        self.assertEqual(
            timezone.localtime(sale.date_added).strftime("%Y-%m-%d %H:%M"),
            txn_date.strftime("%Y-%m-%d %H:%M"),
        )

    def test_vendor_bill_in_appears_in_ledger(self):
        purchase = create_payable_quick_entry(
            self.vendor,
            bill_number="SI/0808",
            net_amount=Decimal("3000"),
            order_date=timezone.now(),
        )
        rows, balance = get_vendor_ledger_rows(self.vendor)
        self.assertEqual(balance, Decimal("3000"))
        self.assertTrue(any(row["reference"] == "SI/0808" for row in rows))
        self.assertEqual(purchase.lines.count(), 1)

    def test_opening_balance_is_first_in_vendor_ledger(self):
        from transactions.models import VendorPayment

        old_date = timezone.localtime().replace(
            year=2020, month=1, day=1, hour=10, minute=0, second=0, microsecond=0
        )
        purchase = create_payable_quick_entry(
            self.vendor,
            bill_number="OLD-1",
            net_amount=Decimal("1000"),
            order_date=old_date,
        )
        VendorPayment.objects.create(
            purchase=purchase,
            amount=Decimal("200"),
            method="cash",
            paid_at=old_date,
        )
        self.vendor.opening_balance = Decimal("5000")
        self.vendor.opening_balance_date = timezone.localtime()
        self.vendor.save(update_fields=["opening_balance", "opening_balance_date"])
        rows, balance = get_vendor_ledger_rows(self.vendor)
        self.assertEqual(rows[0]["type"], "Opening balance")
        self.assertEqual(rows[0]["balance"], Decimal("5000"))
        self.assertEqual(balance, Decimal("5800"))

    def test_account_transaction_form_requires_date(self):
        form = CustomerAccountTransactionForm(
            {
                "transaction_type": "sale_in",
                "amount": "100",
                "method": "cash",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("transaction_date", form.errors)

    def test_save_all_ledger_dates_updates_each_row(self):
        sale = create_receivable_quick_entry(
            self.customer,
            amount=Decimal("1000"),
            sale_date=timezone.now(),
        )
        payment = CustomerPayment.objects.create(
            sale=sale,
            amount=Decimal("200"),
            method="cash",
        )
        sale_target = timezone.localtime().replace(
            year=2025, month=1, day=15, hour=9, minute=30, second=0, microsecond=0
        )
        payment_target = timezone.localtime().replace(
            year=2025, month=2, day=10, hour=11, minute=0, second=0, microsecond=0
        )
        post = QueryDict(mutable=True)
        post.setlist(
            "ledger_date_kind",
            ["sale", "customer_payment"],
        )
        post.setlist(
            "ledger_date_id",
            [str(sale.pk), str(payment.pk)],
        )
        post.setlist(
            "ledger_date_value",
            [
                sale_target.strftime("%Y-%m-%dT%H:%M"),
                payment_target.strftime("%Y-%m-%dT%H:%M"),
            ],
        )
        ok, msg = save_all_ledger_dates("customer", self.customer, post)
        self.assertTrue(ok)
        sale.refresh_from_db()
        payment.refresh_from_db()
        self.assertEqual(
            timezone.localtime(sale.date_added).strftime("%Y-%m-%d %H:%M"),
            sale_target.strftime("%Y-%m-%d %H:%M"),
        )
        self.assertEqual(
            timezone.localtime(payment.received_at).strftime("%Y-%m-%d %H:%M"),
            payment_target.strftime("%Y-%m-%d %H:%M"),
        )

    def test_save_all_ledger_dates_via_view(self):
        purchase = create_payable_quick_entry(
            self.vendor,
            bill_number="B-1",
            net_amount=Decimal("500"),
            order_date=timezone.now(),
        )
        target = timezone.localtime().replace(
            year=2025, month=3, day=20, hour=14, minute=0, second=0, microsecond=0
        )
        url = reverse("vendor-detail", args=[self.vendor.pk])
        response = self.client.post(
            url,
            {
                "action": "save_all_transaction_dates",
                "ledger_date_kind": "purchase",
                "ledger_date_id": str(purchase.pk),
                "ledger_date_value": target.strftime("%Y-%m-%dT%H:%M"),
            },
        )
        self.assertEqual(response.status_code, 302)
        purchase.refresh_from_db()
        self.assertEqual(
            timezone.localtime(purchase.order_date).strftime("%Y-%m-%d %H:%M"),
            target.strftime("%Y-%m-%d %H:%M"),
        )

    def test_save_bulk_purchase_dates(self):
        purchase = create_payable_quick_entry(
            self.vendor,
            bill_number="PB-1",
            net_amount=Decimal("800"),
            order_date=timezone.now(),
        )
        target = timezone.localtime().replace(
            year=2024, month=11, day=5, hour=8, minute=15, second=0, microsecond=0
        )
        post = QueryDict(mutable=True)
        post.setlist("ledger_date_kind", ["purchase"])
        post.setlist("ledger_date_id", [str(purchase.pk)])
        post.setlist("ledger_date_value", [target.strftime("%Y-%m-%dT%H:%M")])
        ok, _ = save_bulk_purchase_dates(post)
        self.assertTrue(ok)
        purchase.refresh_from_db()
        self.assertEqual(
            timezone.localtime(purchase.order_date).strftime("%Y-%m-%d %H:%M"),
            target.strftime("%Y-%m-%d %H:%M"),
        )

    def test_payment_in_without_unpaid_sales_creates_entry(self):
        url = reverse("customer-detail", args=[self.customer.pk])
        txn_date = timezone.localtime().replace(
            year=2026, month=5, day=1, hour=12, minute=0, second=0, microsecond=0
        )
        response = self.client.post(
            url,
            {
                "action": "account_transaction",
                "transaction_type": "payment_in",
                "amount": "1500",
                "reference": "PIN-1",
                "method": "cash",
                "transaction_date": txn_date.strftime("%Y-%m-%dT%H:%M"),
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Sale.objects.filter(customer=self.customer).count(), 1)
        sale = Sale.objects.get(customer=self.customer)
        self.assertEqual(sale.grand_total, Decimal("1500"))
        self.assertEqual(sale.amount_paid, Decimal("1500"))

    def test_payment_out_without_bills_creates_entry(self):
        url = reverse("vendor-detail", args=[self.vendor.pk])
        txn_date = timezone.localtime().replace(
            year=2026, month=5, day=2, hour=12, minute=0, second=0, microsecond=0
        )
        response = self.client.post(
            url,
            {
                "action": "account_transaction",
                "transaction_type": "payment_out",
                "amount": "900",
                "reference": "POUT-1",
                "method": "cash",
                "transaction_date": txn_date.strftime("%Y-%m-%dT%H:%M"),
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Purchase.objects.filter(vendor=self.vendor).count(), 1)

    def test_vendor_account_transaction_form_requires_date(self):
        form = VendorAccountTransactionForm(
            {
                "transaction_type": "bill_in",
                "amount": "100",
                "method": "cash",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("transaction_date", form.errors)
