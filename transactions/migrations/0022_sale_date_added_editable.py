from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("transactions", "0021_sale_import_reference"),
    ]

    operations = [
        migrations.AlterField(
            model_name="sale",
            name="date_added",
            field=models.DateTimeField(
                default=django.utils.timezone.now,
                verbose_name="Sale Date",
            ),
        ),
    ]
