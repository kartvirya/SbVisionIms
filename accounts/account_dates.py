"""Update transaction dates from customer/supplier account pages."""

from django.shortcuts import get_object_or_404

from transactions.models import CustomerPayment, Purchase, Sale, VendorPayment

from .datetime_utils import parse_posted_datetime


def apply_payment_date(payment, party_type, posted_value):
    """Set received_at / paid_at when a date is posted."""
    dt = parse_posted_datetime(posted_value)
    if not dt:
        return
    if party_type == "customer":
        payment.received_at = dt
        payment.save(update_fields=["received_at"])
    else:
        payment.paid_at = dt
        payment.save(update_fields=["paid_at"])


def update_account_transaction_date(party_type, party, date_kind, object_id, posted_value):
    """Update a ledger-linked date. Returns (success, message)."""
    dt = parse_posted_datetime(posted_value)
    if not dt:
        return False, "Enter a valid date."

    if party_type == "customer":
        if date_kind == "sale":
            sale = get_object_or_404(Sale, pk=object_id, customer=party)
            Sale.objects.filter(pk=sale.pk).update(date_added=dt)
            return True, f"Sale #{sale.pk} date updated."
        if date_kind == "customer_payment":
            payment = get_object_or_404(
                CustomerPayment,
                pk=object_id,
                sale__customer=party,
            )
            payment.received_at = dt
            payment.save(update_fields=["received_at"])
            return True, "Payment date updated."
    else:
        if date_kind == "purchase":
            purchase = get_object_or_404(Purchase, pk=object_id, vendor=party)
            Purchase.objects.filter(pk=purchase.pk).update(order_date=dt)
            return True, f"Bill {purchase.display_bill_number} date updated."
        if date_kind == "vendor_payment":
            payment = get_object_or_404(
                VendorPayment,
                pk=object_id,
                purchase__vendor=party,
            )
            payment.paid_at = dt
            payment.save(update_fields=["paid_at"])
            return True, "Payment date updated."

    return False, "Unknown transaction type."
