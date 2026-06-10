from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0008_pan_number'),
    ]

    operations = [
        migrations.CreateModel(
            name='Brand',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, verbose_name='Brand name')),
                ('notes', models.CharField(blank=True, help_text='Optional note about this brand.', max_length=255, verbose_name='Notes')),
                ('is_active', models.BooleanField(default=True, verbose_name='Active')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('vendor', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='brands', to='accounts.vendor', verbose_name='Supplier')),
            ],
            options={
                'verbose_name': 'Brand',
                'verbose_name_plural': 'Brands',
                'ordering': ['name'],
            },
        ),
        migrations.AddConstraint(
            model_name='brand',
            constraint=models.UniqueConstraint(fields=('vendor', 'name'), name='unique_brand_per_vendor'),
        ),
    ]
