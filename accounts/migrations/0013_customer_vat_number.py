from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0012_account_ledger_fixes'),
    ]

    operations = [
        migrations.AddField(
            model_name='customer',
            name='vat_number',
            field=models.CharField(
                blank=True,
                help_text='VAT registration number (optional)',
                max_length=20,
                null=True,
                verbose_name='VAT number',
            ),
        ),
    ]
