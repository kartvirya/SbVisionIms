"""Customer and supplier account transaction ledgers."""

from decimal import Decimal

from django.db.models import Sum
from django.urls import reverse

from accounts.models import Customer, Vendor
from transactions.models import (
    CustomerPayment,
    Purchase,
    PurchaseReturn,
    Sale,
    SaleReturn,
    VendorPayment,
)


def _d(value):
    return Decimal(str(value or 0))


def should_show_opening_balance(opening, adjustment):
    """Hide opening in lists once a manual balance adjustment has been recorded."""
    return _d(opening) != 0 and _d(adjustment) == 0


def get_customer_ledger_rows(customer: Customer):
    """Chronological ledger: opening balance, sales, returns, payments."""
    rows = []
    opening = _d(customer.opening_balance)
    if opening != 0:
        rows.append(
            {
                "date": customer.opening_balance_date,
                "type": "Opening balance",
                "reference": "—",
                "debit": opening if opening > 0 else Decimal("0"),
                "credit": abs(opening) if opening < 0 else Decimal("0"),
                "method": "",
                "url": "",
                "date_kind": "opening_balance",
                "date_pk": customer.pk,
            }
        )

    adjustment = _d(customer.receivables_adjustment)
    if adjustment != 0:
        rows.append(
            {
                "date": None,
                "type": "Balance adjustment",
                "reference": "Manual",
                "debit": adjustment if adjustment > 0 else Decimal("0"),
                "credit": abs(adjustment) if adjustment < 0 else Decimal("0"),
                "method": "",
                "url": "",
            }
        )

    for sale in (
        Sale.objects.filter(customer=customer, is_account_receipt_only=False)
        .order_by("date_added", "id")
    ):
        rows.append(
            {
                "date": sale.date_added,
                "type": "Sale",
                "reference": f"#{sale.id}",
                "debit": _d(sale.grand_total),
                "credit": Decimal("0"),
                "method": "",
                "url": reverse("sale-detail", kwargs={"pk": sale.pk}),
                "edit_url": reverse("sale-update", kwargs={"pk": sale.pk}),
                "date_kind": "sale",
                "date_pk": sale.pk,
            }
        )

    for ret in (
        SaleReturn.objects.filter(sale__customer=customer)
        .select_related("sale")
        .order_by("created_at", "id")
    ):
        rows.append(
            {
                "date": ret.created_at,
                "type": "Sale return",
                "reference": f"Sale #{ret.sale_id}",
                "debit": Decimal("0"),
                "credit": _d(ret.total_credit),
                "method": "",
                "url": reverse("sale-detail", kwargs={"pk": ret.sale_id}),
            }
        )

    for payment in (
        CustomerPayment.objects.filter(sale__customer=customer)
        .select_related("sale")
        .order_by("received_at", "id")
    ):
        rows.append(
            {
                "date": payment.received_at,
                "type": "Payment received",
                "reference": f"Sale #{payment.sale_id}",
                "debit": Decimal("0"),
                "credit": _d(payment.amount),
                "method": payment.get_method_display(),
                "url": reverse("sale-detail", kwargs={"pk": payment.sale_id}),
                "date_kind": "customer_payment",
                "date_pk": payment.pk,
            }
        )

    rows.sort(key=lambda r: (r["date"] is None, r["date"] or customer.pk))
    balance = Decimal("0")
    for row in rows:
        balance += _d(row["debit"]) - _d(row["credit"])
        row["balance"] = balance
    return rows, balance


def get_vendor_ledger_rows(vendor: Vendor):
    """Chronological ledger: opening balance, purchases, returns, payments, adjustments."""
    rows = []
    opening = _d(vendor.opening_balance)
    if opening != 0:
        rows.append(
            {
                "date": vendor.opening_balance_date,
                "type": "Opening balance",
                "reference": "—",
                "debit": abs(opening) if opening < 0 else Decimal("0"),
                "credit": opening if opening > 0 else Decimal("0"),
                "method": "",
                "url": "",
                "date_kind": "opening_balance",
                "date_pk": vendor.pk,
            }
        )

    adjustment = _d(vendor.payables_adjustment)
    if adjustment != 0:
        rows.append(
            {
                "date": None,
                "type": "Payables adjustment",
                "reference": "Manual",
                "debit": abs(adjustment) if adjustment < 0 else Decimal("0"),
                "credit": adjustment if adjustment > 0 else Decimal("0"),
                "method": "",
                "url": "",
            }
        )

    for purchase in (
        Purchase.objects.filter(vendor=vendor, is_account_payment_only=False)
        .order_by("order_date", "id")
    ):
        rows.append(
            {
                "date": purchase.order_date,
                "type": "Purchase",
                "reference": purchase.display_bill_number,
                "debit": Decimal("0"),
                "credit": _d(purchase.net_amount),
                "method": "",
                "url": reverse("purchase-detail", kwargs={"slug": purchase.slug}),
                "edit_url": reverse("purchase-update", kwargs={"pk": purchase.pk}),
                "date_kind": "purchase",
                "date_pk": purchase.pk,
            }
        )

    for ret in (
        PurchaseReturn.objects.filter(purchase__vendor=vendor)
        .select_related("purchase")
        .order_by("created_at", "id")
    ):
        rows.append(
            {
                "date": ret.created_at,
                "type": "Purchase return",
                "reference": ret.purchase.display_bill_number,
                "debit": _d(ret.total_credit),
                "credit": Decimal("0"),
                "method": "",
                "url": reverse("purchase-detail", kwargs={"slug": ret.purchase.slug}),
            }
        )

    for payment in (
        VendorPayment.objects.filter(purchase__vendor=vendor)
        .select_related("purchase")
        .order_by("paid_at", "id")
    ):
        rows.append(
            {
                "date": payment.paid_at,
                "type": "Payment made",
                "reference": payment.purchase.display_bill_number,
                "debit": _d(payment.amount),
                "credit": Decimal("0"),
                "method": payment.get_method_display(),
                "url": reverse("purchase-detail", kwargs={"slug": payment.purchase.slug}),
                "date_kind": "vendor_payment",
                "date_pk": payment.pk,
            }
        )

    rows.sort(key=lambda r: (r["date"] is None, r["date"] or vendor.pk))
    balance = Decimal("0")
    for row in rows:
        balance += _d(row["credit"]) - _d(row["debit"])
        row["balance"] = balance
    return rows, balance


def get_customer_balance_due(customer: Customer):
    sales_total = Sale.objects.filter(customer=customer).aggregate(
        s=Sum("grand_total")
    )["s"] or Decimal("0")
    paid_total = CustomerPayment.objects.filter(sale__customer=customer).aggregate(
        s=Sum("amount")
    )["s"] or Decimal("0")
    returns_total = SaleReturn.objects.filter(sale__customer=customer).aggregate(
        s=Sum("total_credit")
    )["s"] or Decimal("0")
    return (
        _d(customer.opening_balance)
        + _d(customer.receivables_adjustment)
        + _d(sales_total)
        - _d(returns_total)
        - _d(paid_total)
    )


def update_customer_receivables_adjustment(customer_id, amount, sign="+"):
    """Persist manual customer balance adjustment (+ sets adjustment, − applies credit to sales)."""
    from transactions.services import allocate_customer_credit_to_sales

    customer = Customer.objects.get(pk=customer_id)
    value = abs(_d(amount))
    if sign == "-":
        applied = allocate_customer_credit_to_sales(customer, value)
        remainder = value - applied
        if remainder > 0:
            customer.receivables_adjustment = (
                _d(customer.receivables_adjustment) - remainder
            )
    else:
        customer.receivables_adjustment = value
    customer.save(update_fields=["receivables_adjustment"])
    return customer


def get_vendor_balance_due(vendor: Vendor):
    purchases_total = Purchase.objects.filter(vendor=vendor).aggregate(
        s=Sum("net_amount")
    )["s"] or Decimal("0")
    paid_total = VendorPayment.objects.filter(purchase__vendor=vendor).aggregate(
        s=Sum("amount")
    )["s"] or Decimal("0")
    returns_total = PurchaseReturn.objects.filter(purchase__vendor=vendor).aggregate(
        s=Sum("total_credit")
    )["s"] or Decimal("0")
    return (
        _d(vendor.opening_balance)
        + _d(vendor.payables_adjustment)
        + _d(purchases_total)
        - _d(returns_total)
        - _d(paid_total)
    )
