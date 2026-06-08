from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0007_customer_receivables_adjustment'),
    ]

    operations = [
        migrations.AddField(
            model_name='customer',
            name='pan_number',
            field=models.CharField(
                blank=True,
                help_text='PAN / tax ID (optional)',
                max_length=20,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='vendor',
            name='pan_number',
            field=models.CharField(
                blank=True,
                help_text='PAN / tax ID (optional)',
                max_length=20,
                null=True,
            ),
        ),
    ]
