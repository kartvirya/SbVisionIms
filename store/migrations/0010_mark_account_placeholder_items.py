from django.db import migrations


ACCOUNT_BILL_ITEM_NAME = "Account bill entry"
ACCOUNT_CATEGORY_NAME = "Account entries"


def mark_account_placeholder_items(apps, schema_editor):
    Category = apps.get_model("store", "Category")
    Item = apps.get_model("store", "Item")
    PurchaseLine = apps.get_model("transactions", "PurchaseLine")
    Purchase = apps.get_model("transactions", "Purchase")

    category, _ = Category.objects.get_or_create(name=ACCOUNT_CATEGORY_NAME)
    placeholders = list(Item.objects.filter(name=ACCOUNT_BILL_ITEM_NAME))
    if not placeholders:
        return

    canonical = placeholders[0]
    Item.objects.filter(pk=canonical.pk).update(
        is_account_placeholder=True,
        category_id=category.pk,
        vendor_id=None,
        quantity=0,
    )

    for item in placeholders[1:]:
        PurchaseLine.objects.filter(item_id=item.pk).update(item_id=canonical.pk)
        Purchase.objects.filter(item_id=item.pk).update(item_id=canonical.pk)
        item.delete()


class Migration(migrations.Migration):

    dependencies = [
        ("store", "0009_item_is_account_placeholder"),
        ("transactions", "0017_contact_ledger_and_sale_payment"),
    ]

    operations = [
        migrations.RunPython(mark_account_placeholder_items, migrations.RunPython.noop),
    ]
