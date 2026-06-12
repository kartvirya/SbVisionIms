"""Customer and supplier account transaction ledgers."""

from decimal import Decimal

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


def _row_amount_meta(debit, credit, row_kind, row_pk, *, can_edit=True, can_delete=True):
    debit = _d(debit)
    credit = _d(credit)
    if debit > 0:
        amount = debit
        amount_side = "debit"
    else:
        amount = credit
        amount_side = "credit"
    return {
        "row_kind": row_kind,
        "row_pk": row_pk,
        "amount": amount,
        "amount_side": amount_side,
        "can_edit_amount": can_edit and amount > 0,
        "can_delete": can_delete,
    }


def _finalize_customer_ledger_rows(rows, party_pk):
    """Opening balance always first, then adjustments, then dated rows."""
    opening = [r for r in rows if r.get("date_kind") == "opening_balance"]
    adjustments = [
        r for r in rows if "adjustment" in (r.get("type") or "").lower()
    ]
    rest = [r for r in rows if r not in opening and r not in adjustments]
    rest.sort(key=lambda r: (r["date"] is None, r["date"] or party_pk))
    ordered = opening + adjustments + rest
    balance = Decimal("0")
    for row in ordered:
        balance += _d(row["debit"]) - _d(row["credit"])
        row["balance"] = balance
    return ordered, balance


def _finalize_vendor_ledger_rows(rows, party_pk):
    """Opening balance always first, then adjustments, then dated rows."""
    opening = [r for r in rows if r.get("date_kind") == "opening_balance"]
    adjustments = [
        r for r in rows if "adjustment" in (r.get("type") or "").lower()
    ]
    rest = [r for r in rows if r not in opening and r not in adjustments]
    rest.sort(key=lambda r: (r["date"] is None, r["date"] or party_pk))
    ordered = opening + adjustments + rest
    balance = Decimal("0")
    for row in ordered:
        balance += _d(row["credit"]) - _d(row["debit"])
        row["balance"] = balance
    return ordered, balance


def should_show_opening_balance(opening, adjustment):
    """Show opening balance in account lists whenever it is set."""
    return _d(opening) != 0


def opening_balance_display(opening, party_type="vendor"):
    """Human-readable opening balance for lists (amount is always positive)."""
    value = _d(opening)
    if value == 0:
        return None
    amount = abs(value)
    if party_type == "vendor":
        kind = "Payable" if value > 0 else "Receivable"
    else:
        kind = "Receivable" if value > 0 else "Payable"
    return {"amount": amount, "kind": kind, "signed": value}


def get_customer_ledger_rows(customer: Customer):
    """Chronological ledger: opening balance, sales, returns, payments."""
    rows = []
    opening = _d(customer.opening_balance)
    if opening != 0:
        row = {
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
        row.update(
            _row_amount_meta(
                row["debit"],
                row["credit"],
                "opening_balance",
                customer.pk,
            )
        )
        rows.append(row)

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
        row = {
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
        row.update(
            _row_amount_meta(
                row["debit"],
                row["credit"],
                "sale",
                sale.pk,
            )
        )
        rows.append(row)

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
        row = {
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
        row.update(
            _row_amount_meta(
                row["debit"],
                row["credit"],
                "customer_payment",
                payment.pk,
            )
        )
        rows.append(row)

    return _finalize_customer_ledger_rows(rows, customer.pk)


def get_vendor_ledger_rows(vendor: Vendor):
    """Chronological ledger: opening balance, purchases, returns, payments, adjustments."""
    rows = []
    opening = _d(vendor.opening_balance)
    if opening != 0:
        row = {
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
        row.update(
            _row_amount_meta(
                row["debit"],
                row["credit"],
                "opening_balance",
                vendor.pk,
            )
        )
        rows.append(row)

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
        row = {
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
        row.update(
            _row_amount_meta(
                row["debit"],
                row["credit"],
                "purchase",
                purchase.pk,
            )
        )
        rows.append(row)

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
        row = {
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
        row.update(
            _row_amount_meta(
                row["debit"],
                row["credit"],
                "vendor_payment",
                payment.pk,
            )
        )
        rows.append(row)

    return _finalize_vendor_ledger_rows(rows, vendor.pk)


def get_customer_balance_due(customer: Customer):
    """Closing balance — must match the last row of the account ledger."""
    _, balance = get_customer_ledger_rows(customer)
    return balance


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
    """Closing balance — must match the last row of the account ledger."""
    _, balance = get_vendor_ledger_rows(vendor)
    return balance
