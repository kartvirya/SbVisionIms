"""Update transaction dates from customer/supplier account pages."""

from django.shortcuts import get_object_or_404

from accounts.models import Customer, Vendor
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
        if date_kind == "opening_balance":
            if str(party.pk) != str(object_id):
                return False, "Invalid opening balance row."
            Customer.objects.filter(pk=party.pk).update(opening_balance_date=dt)
            return True, "Opening balance date updated."
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
        if date_kind == "opening_balance":
            if str(party.pk) != str(object_id):
                return False, "Invalid opening balance row."
            Vendor.objects.filter(pk=party.pk).update(opening_balance_date=dt)
            return True, "Opening balance date updated."
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


def save_all_ledger_dates(party_type, party, post_data):
    """Save individually edited dates from the account transaction history form."""
    kinds = post_data.getlist("ledger_date_kind")
    object_ids = post_data.getlist("ledger_date_id")
    values = post_data.getlist("ledger_date_value")

    if not kinds:
        return False, "No editable transaction dates on this account."

    updated = 0
    skipped = 0
    for date_kind, object_id, posted_value in zip(kinds, object_ids, values):
        if not posted_value:
            skipped += 1
            continue
        ok, _ = update_account_transaction_date(
            party_type,
            party,
            date_kind,
            object_id,
            posted_value,
        )
        if ok:
            updated += 1
        else:
            skipped += 1

    if updated == 0:
        return False, "No valid dates to save. Enter a date in at least one row."
    if skipped:
        return True, f"Saved {updated} date(s). Skipped {skipped} row(s) without a valid date."
    return True, f"Saved {updated} date(s)."


def save_bulk_purchase_dates(post_data):
    """Save billed dates edited on the payables book report."""
    kinds = post_data.getlist("ledger_date_kind")
    object_ids = post_data.getlist("ledger_date_id")
    values = post_data.getlist("ledger_date_value")

    if not kinds:
        return False, "No bill dates to save."

    updated = 0
    skipped = 0
    for date_kind, object_id, posted_value in zip(kinds, object_ids, values):
        if date_kind != "purchase" or not posted_value:
            skipped += 1
            continue
        dt = parse_posted_datetime(posted_value)
        if not dt:
            skipped += 1
            continue
        if Purchase.objects.filter(pk=object_id).update(order_date=dt):
            updated += 1
        else:
            skipped += 1

    if updated == 0:
        return False, "No valid bill dates to save."
    if skipped:
        return True, f"Saved {updated} bill date(s). Skipped {skipped} row(s)."
    return True, f"Saved {updated} bill date(s)."
