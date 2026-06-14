from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('transactions', '0019_mark_account_payment_only_entries'),
    ]

    operations = [
        migrations.AlterField(
            model_name='saledetail',
            name='quantity',
            field=models.DecimalField(decimal_places=3, max_digits=12),
        ),
    ]
