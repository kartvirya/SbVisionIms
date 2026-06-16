from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('transactions', '0020_saledetail_decimal_quantity'),
    ]

    operations = [
        migrations.AddField(
            model_name='sale',
            name='import_reference',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Excel sale_reference used to prevent duplicate imports.',
                max_length=100,
            ),
        ),
        migrations.AddConstraint(
            model_name='sale',
            constraint=models.UniqueConstraint(
                condition=~models.Q(import_reference=''),
                fields=('import_reference',),
                name='uniq_sale_import_reference',
            ),
        ),
    ]
