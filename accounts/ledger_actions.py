"""Update or remove rows shown on customer/supplier account ledgers."""

from decimal import Decimal

from django.shortcuts import get_object_or_404
from django.utils import timezone

from accounts.models import Customer, Vendor
from transactions.models import Purchase, VendorPayment


def _d(value):
    return Decimal(str(value or 0))


def _sync_purchase_header_amount(purchase, net_amount):
    """Keep account-book and single-line purchases aligned with the ledger amount."""
    net_amount = _d(net_amount)
    if net_amount < 0:
        raise ValueError("Amount cannot be negative.")
    purchase.sub_total = net_amount
    purchase.discount_amount = Decimal("0")
    purchase.vat_percentage = 0
    purchase.vat_amount = Decimal("0")
    purchase.net_amount = net_amount
    purchase.total_value = net_amount
    line = purchase.lines.first()
    if line and purchase.lines.count() == 1:
        line.quantity = 1
        line.unit_price = net_amount
        line.save()
    elif not purchase.lines.exists() and purchase.item_id:
        purchase.price = net_amount
        purchase.quantity = 1
    purchase.save()


def _vendor_payment_as_bill(payment, amount):
    """Turn a payment-out row into a supplier bill (credit)."""
    purchase = payment.purchase
    payment.delete()
    purchase.is_account_payment_only = False
    purchase.amount_paid = Decimal("0")
    purchase.receipt_status = "P"
    _sync_purchase_header_amount(purchase, amount)
    return f"Converted to bill {purchase.display_bill_number} (credit)."


def _vendor_bill_as_payment(purchase, amount):
    """Turn a supplier bill row into a payment-out (debit)."""
    from transactions.services import ensure_purchase_lines

    ensure_purchase_lines(purchase)
    purchase.is_account_payment_only = True
    purchase.receipt_status = "P"
    purchase.amount_paid = amount
    _sync_purchase_header_amount(purchase, amount)
    purchase.save()
    purchase.vendor_payments.all().delete()
    VendorPayment.objects.create(
        purchase=purchase,
        amount=amount,
        method="cash",
        notes="Converted from bill in account book",
        paid_at=timezone.now(),
    )
    purchase.save()
    return f"Converted to payment out (debit) for {purchase.display_bill_number}."


def update_ledger_row_amount(party_type, party, row_kind, row_pk, amount, amount_side=None):
    """Update an editable ledger amount. Returns (success, message)."""
    value = _d(amount)
    if value < 0:
        return False, "Amount cannot be negative."

    if party_type == "vendor":
        if row_kind == "opening_balance":
            if str(party.pk) != str(row_pk):
                return False, "Invalid opening balance row."
            if amount_side == "debit":
                party.opening_balance = -value
            else:
                party.opening_balance = value
            party.save(update_fields=["opening_balance"])
            return True, "Opening balance amount updated."

        if row_kind == "purchase":
            purchase = get_object_or_404(Purchase, pk=row_pk, vendor=party)
            if amount_side == "debit":
                return True, _vendor_bill_as_payment(purchase, value)
            purchase.is_account_payment_only = False
            _sync_purchase_header_amount(purchase, value)
            return True, f"Bill {purchase.display_bill_number} amount updated."

        if row_kind == "vendor_payment":
            payment = get_object_or_404(
                VendorPayment,
                pk=row_pk,
                purchase__vendor=party,
            )
            if amount_side == "credit":
                return True, _vendor_payment_as_bill(payment, value)
            payment.amount = value
            payment.save(update_fields=["amount"])
            payment.purchase.save()
            return True, "Payment amount updated."

    else:
        if row_kind == "opening_balance":
            if str(party.pk) != str(row_pk):
                return False, "Invalid opening balance row."
            if amount_side == "credit":
                party.opening_balance = -value
            else:
                party.opening_balance = value
            party.save(update_fields=["opening_balance"])
            return True, "Opening balance amount updated."

        if row_kind == "sale":
            from transactions.models import CustomerPayment, Sale

            sale = get_object_or_404(Sale, pk=row_pk, customer=party)
            if amount_side == "credit":
                sale.customer_payments.all().delete()
                sale.is_account_receipt_only = True
                sale.sub_total = value
                sale.grand_total = value
                sale.tax_amount = Decimal("0")
                sale.tax_percentage = 0
                sale.amount_paid = value
                sale.save()
                CustomerPayment.objects.create(
                    sale=sale,
                    amount=value,
                    method="cash",
                    notes=f"Converted from sale #{sale.pk}",
                    received_at=timezone.now(),
                )
                sale.save()
                return True, "Converted to payment received (credit)."
            sale.is_account_receipt_only = False
            sale.sub_total = value
            sale.grand_total = value
            sale.tax_amount = Decimal("0")
            sale.tax_percentage = 0
            sale.save()
            return True, f"Sale #{sale.pk} amount updated."

        if row_kind == "customer_payment":
            from transactions.models import CustomerPayment

            payment = get_object_or_404(
                CustomerPayment,
                pk=row_pk,
                sale__customer=party,
            )
            if amount_side == "debit":
                sale = payment.sale
                payment.delete()
                sale.is_account_receipt_only = False
                sale.sub_total = value
                sale.grand_total = value
                sale.tax_amount = Decimal("0")
                sale.tax_percentage = 0
                sale.amount_paid = Decimal("0")
                sale.save()
                return True, f"Converted to sale #{sale.pk} (debit)."
            payment.amount = value
            payment.save(update_fields=["amount"])
            payment.sale.save()
            return True, "Payment amount updated."

    return False, "This row cannot be edited here."


def delete_ledger_row(party_type, party, row_kind, row_pk):
    """Delete a ledger row where allowed. Returns (success, message)."""
    if party_type == "vendor":
        if row_kind == "opening_balance":
            if str(party.pk) != str(row_pk):
                return False, "Invalid opening balance row."
            party.opening_balance = Decimal("0")
            party.opening_balance_date = None
            party.save(update_fields=["opening_balance", "opening_balance_date"])
            return True, "Opening balance cleared."

        if row_kind == "purchase":
            purchase = get_object_or_404(Purchase, pk=row_pk, vendor=party)
            if purchase.receipt_status == "S" and purchase.inventory_transaction_id:
                return False, "Cannot delete a received bill that posted stock. Reverse receipt first."
            bill = purchase.display_bill_number
            purchase.delete()
            return True, f"Bill {bill} deleted."

        if row_kind == "vendor_payment":
            payment = get_object_or_404(
                VendorPayment,
                pk=row_pk,
                purchase__vendor=party,
            )
            purchase = payment.purchase
            payment.delete()
            if purchase.is_account_payment_only and not purchase.vendor_payments.exists():
                purchase.delete()
            else:
                purchase.save()
            return True, "Payment deleted."

    else:
        if row_kind == "opening_balance":
            if str(party.pk) != str(row_pk):
                return False, "Invalid opening balance row."
            party.opening_balance = Decimal("0")
            party.opening_balance_date = None
            party.save(update_fields=["opening_balance", "opening_balance_date"])
            return True, "Opening balance cleared."

        if row_kind == "sale":
            from transactions.models import Sale

            sale = get_object_or_404(Sale, pk=row_pk, customer=party)
            sale_id = sale.pk
            sale.delete()
            return True, f"Sale #{sale_id} deleted."

        if row_kind == "customer_payment":
            from transactions.models import CustomerPayment

            payment = get_object_or_404(
                CustomerPayment,
                pk=row_pk,
                sale__customer=party,
            )
            sale = payment.sale
            payment.delete()
            sale.save()
            return True, "Payment deleted."

    return False, "This row cannot be deleted here."
