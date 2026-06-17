from django.core.management.base import BaseCommand

from accounts.customer_utils import merge_all_duplicate_customers


class Command(BaseCommand):
    help = "Merge duplicate customer records (same name or phone)."

    def handle(self, *args, **options):
        merged = merge_all_duplicate_customers()
        self.stdout.write(self.style.SUCCESS(f"Merged {merged} duplicate customer(s)."))
