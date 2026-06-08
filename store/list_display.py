"""Helpers for consistent row numbers in paginated list templates."""

from django.shortcuts import redirect


class NormalizePageMixin:
    """Redirect when ?page= is out of range so the URL matches the visible page."""

    def get(self, request, *args, **kwargs):
        requested = request.GET.get("page")
        response = super().get(request, *args, **kwargs)
        if not requested or not getattr(self, "paginate_by", None):
            return response
        page_obj = getattr(response, "context_data", None)
        page_obj = page_obj.get("page_obj") if page_obj else None
        if not page_obj:
            return response
        try:
            if int(requested) != page_obj.number:
                params = request.GET.copy()
                params["page"] = str(page_obj.number)
                return redirect(f"{request.path}?{params.urlencode()}")
        except (TypeError, ValueError):
            params = request.GET.copy()
            params.pop("page", None)
            query = params.urlencode()
            return redirect(f"{request.path}?{query}" if query else request.path)
        return response


def annotate_list_row_numbers(object_list, page_obj=None):
    """
    Attach list_row_number (1..n on this page) so row # updates after deletes.
    """
    if not object_list:
        return object_list
    if page_obj:
        start = (page_obj.number - 1) * page_obj.paginator.per_page + 1
    else:
        start = 1
    for offset, obj in enumerate(object_list):
        obj.list_row_number = start + offset
    return object_list
