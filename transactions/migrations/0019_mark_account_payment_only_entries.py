from django.db import migrations


def mark_payment_only_purchases(apps, schema_editor):
    Purchase = apps.get_model("transactions", "Purchase")
    VendorPayment = apps.get_model("transactions", "VendorPayment")
    for purchase in Purchase.objects.filter(
        description__icontains="Account book payment out",
        is_account_payment_only=False,
    ):
        payments = list(VendorPayment.objects.filter(purchase_id=purchase.pk))
        if (
            len(payments) == 1
            and purchase.net_amount == payments[0].amount
            and purchase.amount_remaining == 0
        ):
            purchase.is_account_payment_only = True
            purchase.save(update_fields=["is_account_payment_only"])


def mark_receipt_only_sales(apps, schema_editor):
    Sale = apps.get_model("transactions", "Sale")
    CustomerPayment = apps.get_model("transactions", "CustomerPayment")
    for sale in Sale.objects.filter(
        is_account_receipt_only=False,
    ):
        payments = list(CustomerPayment.objects.filter(sale_id=sale.pk))
        if not payments:
            continue
        notes = " ".join((payment.notes or "") for payment in payments)
        if "Account book payment in" not in notes:
            continue
        if (
            len(payments) == 1
            and sale.grand_total == payments[0].amount
            and sale.amount_remaining == 0
        ):
            sale.is_account_receipt_only = True
            sale.save(update_fields=["is_account_receipt_only"])


class Migration(migrations.Migration):
    dependencies = [
        ("transactions", "0018_account_ledger_fixes"),
    ]

    operations = [
        migrations.RunPython(mark_payment_only_purchases, migrations.RunPython.noop),
        migrations.RunPython(mark_receipt_only_sales, migrations.RunPython.noop),
    ]
