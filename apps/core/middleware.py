from django.shortcuts import redirect
from django.urls import Resolver404, resolve

# Paths the user must still be able to reach even while locked into the
# forced password-change flow, or they could never actually get out of it.
EXEMPT_URL_NAMES = {
    'accounts:password_change',
    'accounts:logout',
    'admin:logout',
}


class ForcePasswordChangeMiddleware:
    """Redirects any authenticated user with must_change_password=True to
    the change-password page, regardless of which URL they requested.

    Applies site-wide, including /admin/: a temporary password (issued by
    ICT Admin when provisioning an account) shouldn't grant durable access
    anywhere until the owner sets their own password.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        if user is not None and user.is_authenticated and getattr(user, 'must_change_password', False):
            if not self._is_exempt(request.path):
                return redirect('accounts:password_change')
        return self.get_response(request)

    def _is_exempt(self, path):
        if path.startswith('/static/') or path.startswith('/media/'):
            return True
        try:
            match = resolve(path)
        except Resolver404:
            return False
        url_name = f'{match.namespace}:{match.url_name}' if match.namespace else match.url_name
        return url_name in EXEMPT_URL_NAMES
