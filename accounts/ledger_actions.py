"""Update or remove rows shown on customer/supplier account ledgers."""

from decimal import Decimal

from django.shortcuts import get_object_or_404

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


def update_ledger_row_amount(party_type, party, row_kind, row_pk, amount):
    """Update an editable ledger amount. Returns (success, message)."""
    value = _d(amount)
    if value < 0:
        return False, "Amount cannot be negative."

    if party_type == "vendor":
        if row_kind == "opening_balance":
            if str(party.pk) != str(row_pk):
                return False, "Invalid opening balance row."
            existing = _d(party.opening_balance)
            if existing < 0:
                party.opening_balance = -value
            else:
                party.opening_balance = value
            party.save(update_fields=["opening_balance"])
            return True, "Opening balance amount updated."

        if row_kind == "purchase":
            purchase = get_object_or_404(Purchase, pk=row_pk, vendor=party)
            _sync_purchase_header_amount(purchase, value)
            return True, f"Bill {purchase.display_bill_number} amount updated."

        if row_kind == "vendor_payment":
            payment = get_object_or_404(
                VendorPayment,
                pk=row_pk,
                purchase__vendor=party,
            )
            payment.amount = value
            payment.save(update_fields=["amount"])
            payment.purchase.save()
            return True, "Payment amount updated."

    else:
        if row_kind == "opening_balance":
            if str(party.pk) != str(row_pk):
                return False, "Invalid opening balance row."
            existing = _d(party.opening_balance)
            if existing < 0:
                party.opening_balance = -value
            else:
                party.opening_balance = value
            party.save(update_fields=["opening_balance"])
            return True, "Opening balance amount updated."

        if row_kind == "sale":
            from transactions.models import Sale

            sale = get_object_or_404(Sale, pk=row_pk, customer=party)
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
