"""Parse and format datetimes for account book date fields."""

from django.utils import timezone
from django.utils.dateparse import parse_datetime


DATETIME_LOCAL_FORMAT = "%Y-%m-%dT%H:%M"


def parse_posted_datetime(value):
    """Parse datetime-local POST value into a timezone-aware datetime."""
    if not value:
        return None
    dt = parse_datetime(str(value).strip())
    if not dt:
        return None
    if timezone.is_naive(dt):
        return timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


def format_datetime_local(dt):
    """Format a datetime for datetime-local inputs."""
    if not dt:
        return ""
    return timezone.localtime(dt).strftime(DATETIME_LOCAL_FORMAT)


def resolve_posted_transaction_date(request, form=None):
    """Read a transaction date from a bound form or raw POST."""
    if form is not None and hasattr(form, "cleaned_data"):
        dt = form.cleaned_data.get("transaction_date")
        if dt:
            return dt
    if form is not None and hasattr(form, "data"):
        dt = parse_posted_datetime(form.data.get("transaction_date"))
        if dt:
            return dt
    return parse_posted_datetime(request.POST.get("transaction_date"))
