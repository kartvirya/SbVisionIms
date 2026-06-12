def return_query(request):
    """Expose current GET query string for links and forms."""
    return {"return_query": request.GET.urlencode()}
