from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


def _format_indian_number(value, decimals=2):
    try:
        amount = Decimal(str(value or 0))
    except (InvalidOperation, TypeError, ValueError):
        amount = Decimal("0")
    quant = Decimal("1." + "0" * decimals)
    amount = amount.quantize(quant)
    sign = "-" if amount < 0 else ""
    amount = abs(amount)
    text = f"{amount:.{decimals}f}"
    integer, _, fraction = text.partition(".")
    if len(integer) <= 3:
        grouped = integer
    else:
        last3 = integer[-3:]
        rest = integer[:-3]
        parts = []
        while len(rest) > 2:
            parts.insert(0, rest[-2:])
            rest = rest[:-2]
        if rest:
            parts.insert(0, rest)
        grouped = ",".join(parts) + "," + last3
    return f"{sign}{grouped}.{fraction}"


@register.filter
def indian_number(value, decimals=2):
    """Format a number using Indian digit grouping (e.g. 2,33,299.69)."""
    try:
        decimals = int(decimals)
    except (TypeError, ValueError):
        decimals = 2
    return _format_indian_number(value, decimals)


@register.simple_tag
def purchase_taxable_amount(purchase):
    try:
        sub_total = Decimal(str(purchase.sub_total or 0))
        discount = Decimal(str(purchase.discount_amount or 0))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")
    taxable = sub_total - discount
    return taxable if taxable > 0 else Decimal("0")
