from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0009_vendorbrand'),
        ('store', '0007_todo_batch'),
    ]

    operations = [
        migrations.AddField(
            model_name='item',
            name='hs_code',
            field=models.CharField(
                blank=True,
                help_text='Harmonized System / customs tariff code (optional).',
                max_length=20,
                verbose_name='HS code',
            ),
        ),
        migrations.AddField(
            model_name='item',
            name='brand',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='items',
                to='accounts.brand',
                verbose_name='Brand',
            ),
        ),
    ]
