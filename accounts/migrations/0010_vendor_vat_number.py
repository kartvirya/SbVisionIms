from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0009_vendorbrand'),
    ]

    operations = [
        migrations.AddField(
            model_name='vendor',
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
