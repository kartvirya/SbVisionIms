from django.db import migrations, models
from django.utils import timezone


class Migration(migrations.Migration):

    dependencies = [
        ("transactions", "0011_purchase_bill_number"),
    ]

    operations = [
        migrations.AlterField(
            model_name="purchase",
            name="order_date",
            field=models.DateTimeField(
                default=timezone.now,
                verbose_name="Billed date",
            ),
        ),
    ]
