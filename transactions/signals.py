from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from transactions.models import CustomerPayment, Purchase, Sale, VendorPayment
from transactions.services import (
    delete_payment_ledger,
    post_customer_payment_ledger,
    post_vendor_payment_ledger,
)


@receiver(post_save, sender=VendorPayment)
def vendor_payment_post_save(sender, instance, raw=False, **kwargs):
    if raw:
        return
    p = Purchase.objects.get(pk=instance.purchase_id)
    p.save()
    post_vendor_payment_ledger(payment=instance)


@receiver(post_delete, sender=VendorPayment)
def vendor_payment_post_delete(sender, instance, **kwargs):
    delete_payment_ledger(instance)
    if Purchase.objects.filter(pk=instance.purchase_id).exists():
        p = Purchase.objects.get(pk=instance.purchase_id)
        p.save()


@receiver(post_save, sender=CustomerPayment)
def customer_payment_post_save(sender, instance, raw=False, **kwargs):
    if raw:
        return
    s = Sale.objects.get(pk=instance.sale_id)
    s.save()
    post_customer_payment_ledger(payment=instance)


@receiver(post_delete, sender=CustomerPayment)
def customer_payment_post_delete(sender, instance, **kwargs):
    delete_payment_ledger(instance)
    if Sale.objects.filter(pk=instance.sale_id).exists():
        s = Sale.objects.get(pk=instance.sale_id)
        s.save()
