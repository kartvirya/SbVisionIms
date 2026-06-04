"""Helpers for consistent row numbers in paginated list templates."""


def annotate_list_row_numbers(object_list, page_obj=None):
    """
    Attach list_row_number (1..n on this page) so row # updates after deletes.
    """
    if not object_list:
        return object_list
    start = page_obj.start_index() if page_obj else 1
    for offset, obj in enumerate(object_list):
        obj.list_row_number = start + offset
    return object_list
