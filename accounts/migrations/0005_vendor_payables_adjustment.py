from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0004_alter_logistics_phone_number"),
    ]

    operations = [
        migrations.AddField(
            model_name="vendor",
            name="payables_adjustment",
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text="Manual adjustment (+/-) applied on the payables aging report.",
                max_digits=12,
                verbose_name="Payables adjustment",
            ),
        ),
    ]
