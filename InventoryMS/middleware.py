"""Request middleware for mounting IMS under a URL prefix (e.g. /ims)."""


class SubpathScriptNameMiddleware:
    """
    When requests arrive with a prefix (FORCE_SCRIPT_NAME), set SCRIPT_NAME and
    strip PATH_INFO so URLConf stays at root while {% url %} / redirects keep
    the public prefix. WhiteNoise still sees the full request.path.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from django.conf import settings

        prefix = (getattr(settings, "FORCE_SCRIPT_NAME", None) or "").rstrip("/")
        if prefix:
            path = request.path
            if path == prefix or path.startswith(prefix + "/"):
                request.META["SCRIPT_NAME"] = prefix
                new_info = path[len(prefix) :] or "/"
                request.META["PATH_INFO"] = new_info
                request.path_info = new_info
        return self.get_response(request)
