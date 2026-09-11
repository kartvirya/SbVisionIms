"""
Temporary request diagnostics for Vercel WSGI body/CSRF debugging.
"""
import logging

logger = logging.getLogger(__name__)


class RequestDebugMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method == "POST":
            logger.warning(
                "POST debug path=%s content_type=%s content_length=%s "
                "post_keys=%s body_len=%s origin=%s",
                request.path,
                request.META.get("CONTENT_TYPE"),
                request.META.get("CONTENT_LENGTH"),
                list(request.POST.keys()),
                len(request.body or b""),
                request.META.get("HTTP_ORIGIN"),
            )
        return self.get_response(request)
