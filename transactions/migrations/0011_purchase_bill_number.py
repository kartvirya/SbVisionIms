from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("transactions", "0010_purchase_lines_receipt_gate_payments_links"),
    ]

    operations = [
        migrations.AddField(
            model_name="purchase",
            name="bill_number",
            field=models.CharField(
                blank=True,
                help_text="Supplier invoice or bill reference number.",
                max_length=64,
                verbose_name="Bill number",
            ),
        ),
    ]
