"""Static/media helpers for subpath (/ims) deployments."""

from django.conf import settings
from django.contrib.staticfiles.storage import StaticFilesStorage


class PrefixedStaticFilesStorage(StaticFilesStorage):
    """Serve at /static/ on the app; expose /ims/static/ in generated URLs."""

    def url(self, name):
        url = super().url(name)
        prefix = (getattr(settings, "FORCE_SCRIPT_NAME", None) or "").rstrip("/")
        if prefix and url.startswith("/"):
            return f"{prefix}{url}"
        return url
