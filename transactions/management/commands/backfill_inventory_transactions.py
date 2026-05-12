from django.core.management.base import BaseCommand
from django.db import transaction

from transactions.models import Purchase, Sale
from transactions.services import (
    create_sale_transaction,
    sync_purchase_inventory_transaction,
    sync_item_quantity_cache,
)
from store.models import Item


class Command(BaseCommand):
    help = (
        "Backfill Sale/Purchase data into unified inventory transactions, "
        "then sync Item.quantity cache from stock movements."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Simulate backfill and rollback at the end.",
        )

    def handle(self, *args, **options):
        purchases_created = 0
        sales_created = 0
        dry_run = options.get("dry_run", False)

        with transaction.atomic():
            purchases = (
                Purchase.objects.select_related("vendor")
                .prefetch_related("lines__item")
                .filter(inventory_transaction__isnull=True, receipt_status="S")
            )
            for purchase in purchases.iterator():
                txn = sync_purchase_inventory_transaction(
                    purchase=purchase,
                    notes_suffix=" (backfill)",
                )
                if txn is not None:
                    purchases_created += 1

            sales = Sale.objects.select_related("customer").prefetch_related(
                "saledetail_set__item"
            ).filter(inventory_transaction__isnull=True)
            for sale in sales:
                sale_items = []
                for detail in sale.saledetail_set.all():
                    sale_items.append(
                        {
                            "item": detail.item_id,
                            "quantity": detail.quantity,
                            "unit_price": detail.price,
                        }
                    )

                inventory_transaction = create_sale_transaction(
                    customer=sale.customer,
                    items=sale_items,
                    notes=f"Backfill sale #{sale.id}",
                )
                sale.inventory_transaction = inventory_transaction
                sale.save(update_fields=["inventory_transaction"])
                sales_created += 1

            sync_item_quantity_cache(Item.objects.all())
            if dry_run:
                transaction.set_rollback(True)

        status = "DRY RUN complete" if dry_run else "Backfill complete"
        self.stdout.write(
            self.style.SUCCESS(
                f"{status}. Purchases linked: {purchases_created}, "
                f"Sales linked: {sales_created}."
            )
        )
