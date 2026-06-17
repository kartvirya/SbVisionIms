"""Find, create, and merge customer records by identity."""

from django.db import transaction
from django.db.models import Q


def _norm_name(value):
    return (value or "").strip()


def customer_identity_key(first_name, last_name=None, phone=None):
    """Stable key for grouping duplicate customers."""
    phone = (phone or "").strip()
    if phone:
        return f"phone:{phone}"
    first = _norm_name(first_name).lower()
    last = _norm_name(last_name).lower()
    return f"name:{first}:{last}"


def find_customer_by_identity(*, first_name, last_name=None, phone=None):
    from accounts.models import Customer

    first = _norm_name(first_name)
    if not first:
        return None

    phone = (phone or "").strip() or None
    if phone:
        match = Customer.objects.filter(phone=phone).order_by("id").first()
        if match:
            return match

    qs = Customer.objects.filter(first_name__iexact=first)
    last = _norm_name(last_name) or None
    if last:
        qs = qs.filter(last_name__iexact=last)
    else:
        qs = qs.filter(Q(last_name__isnull=True) | Q(last_name=""))
    return qs.order_by("id").first()


def get_or_create_customer_by_identity(
    *,
    first_name,
    last_name=None,
    phone=None,
    defaults=None,
):
    from accounts.models import Customer

    defaults = defaults or {}
    customer = find_customer_by_identity(
        first_name=first_name,
        last_name=last_name,
        phone=phone,
    )
    if customer:
        updates = []
        phone = (phone or "").strip() or None
        if phone and not customer.phone:
            customer.phone = phone
            updates.append("phone")
        for field in ("email", "address", "pan_number", "vat_number"):
            value = defaults.get(field)
            if value and not getattr(customer, field):
                setattr(customer, field, value)
                updates.append(field)
        if updates:
            customer.save(update_fields=updates)
        return customer, False

    customer = Customer.objects.create(
        first_name=_norm_name(first_name),
        last_name=_norm_name(last_name) or None,
        phone=(phone or "").strip() or None,
        email=defaults.get("email") or None,
        address=defaults.get("address") or None,
        pan_number=defaults.get("pan_number") or None,
        vat_number=defaults.get("vat_number") or None,
        opening_balance=defaults.get("opening_balance", 0),
    )
    return customer, True


@transaction.atomic
def merge_customer_into(canonical, duplicate):
    """Move all records from duplicate onto canonical, then delete duplicate."""
    from accounts.models import Customer
    from transactions.models import InventoryTransaction, Sale

    if canonical.pk == duplicate.pk:
        return canonical

    Sale.objects.filter(customer=duplicate).update(customer=canonical)
    InventoryTransaction.objects.filter(customer=duplicate).update(customer=canonical)

    canonical.opening_balance += duplicate.opening_balance
    canonical.receivables_adjustment += duplicate.receivables_adjustment
    canonical.loyalty_points = (canonical.loyalty_points or 0) + (
        duplicate.loyalty_points or 0
    )

    for field in ("phone", "email", "address", "pan_number", "vat_number"):
        if not getattr(canonical, field) and getattr(duplicate, field):
            setattr(canonical, field, getattr(duplicate, field))

    if not canonical.opening_balance_date and duplicate.opening_balance_date:
        canonical.opening_balance_date = duplicate.opening_balance_date

    canonical.save()
    duplicate.delete()
    return Customer.objects.get(pk=canonical.pk)


def merge_all_duplicate_customers():
    """Merge customers that share the same phone or same name (case-insensitive)."""
    from collections import defaultdict

    from accounts.models import Customer

    groups = defaultdict(list)
    for customer in Customer.objects.all().order_by("id"):
        key = customer_identity_key(
            customer.first_name,
            customer.last_name,
            customer.phone,
        )
        groups[key].append(customer)

    merged = 0
    for customers in groups.values():
        if len(customers) < 2:
            continue
        canonical = customers[0]
        for duplicate in customers[1:]:
            merge_customer_into(canonical, duplicate)
            merged += 1
    return merged
