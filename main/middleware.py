from django.http import Http404


class HideDjangoAdminMiddleware:
    """Return 404 for the built-in Django admin unless the user is an active staff member."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path == "/admin" or request.path.startswith("/admin/"):
            user = request.user
            if not user.is_authenticated or not user.is_active or not user.is_staff:
                raise Http404
        return self.get_response(request)
