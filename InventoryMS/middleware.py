"""Request middleware for mounting IMS under a URL prefix (e.g. /ims)."""

from django.conf import settings
from django.urls import set_script_prefix


class SubpathScriptNameMiddleware:
    """
    Ensure reverse()/redirects use FORCE_SCRIPT_NAME when the reverse proxy
    has already stripped the public prefix from PATH_INFO (Next.js /ims rewrite).
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.prefix = (getattr(settings, "FORCE_SCRIPT_NAME", None) or "").rstrip("/")

    def __call__(self, request):
        if self.prefix:
            set_script_prefix(self.prefix + "/")
            request.META["SCRIPT_NAME"] = self.prefix
            # Keep path_info as-is (already stripped by the proxy).
            if hasattr(request, "script_name"):
                request.script_name = self.prefix
        response = self.get_response(request)
        return response
