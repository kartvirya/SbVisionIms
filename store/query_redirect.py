"""Preserve list/filter query strings across POST redirects."""

from django.http import HttpResponseRedirect
from django.shortcuts import redirect


def get_return_query(request):
    """Read filter query string from POST hidden field or current GET."""
    posted = (request.POST.get("return_query") or "").strip()
    if posted:
        return posted
    return request.GET.urlencode()


def redirect_preserving_query(request, url):
    """Redirect to url, appending the active filter query string when present."""
    query = get_return_query(request)
    if query:
        separator = "&" if "?" in url else "?"
        return redirect(f"{url}{separator}{query}")
    return redirect(url)


def url_with_query(url, query_string):
    if not query_string:
        return url
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}{query_string}"


def redirect_response_preserving_query(request, url):
    """HttpResponseRedirect variant for class-based views."""
    query = get_return_query(request)
    return HttpResponseRedirect(url_with_query(url, query))
