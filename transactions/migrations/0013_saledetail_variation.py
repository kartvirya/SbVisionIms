from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("store", "0005_item_cost_price_item_low_stock_threshold_and_more"),
        ("transactions", "0012_alter_purchase_order_date"),
    ]

    operations = [
        migrations.AddField(
            model_name="saledetail",
            name="variation",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="sale_details",
                to="store.productvariation",
            ),
        ),
    ]
