from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("store", "0008_item_hs_code_brand"),
    ]

    operations = [
        migrations.AddField(
            model_name="item",
            name="is_account_placeholder",
            field=models.BooleanField(
                default=False,
                help_text="Internal placeholder for account-book bills; hidden from inventory.",
            ),
        ),
    ]
