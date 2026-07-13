from django.contrib.auth.mixins import AccessMixin, LoginRequiredMixin
from django.core.exceptions import PermissionDenied


class RoleRequiredMixin(LoginRequiredMixin, AccessMixin):
    """Restrict a class-based view to one or more roles.

    Usage: set ``allowed_roles = (Role.HOD, Role.REGISTRAR)`` on the view.
    Superusers always pass.
    """

    allowed_roles: tuple = ()

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        if request.user.is_superuser:
            return super().dispatch(request, *args, **kwargs)

        if not self.allowed_roles:
            raise ImproperlyConfiguredRoleError(self.__class__.__name__)

        if request.user.role not in self.allowed_roles:
            raise PermissionDenied('You do not have permission to access this page.')

        return super().dispatch(request, *args, **kwargs)


class ImproperlyConfiguredRoleError(Exception):
    def __init__(self, view_name):
        super().__init__(
            f'{view_name} uses RoleRequiredMixin but defines no allowed_roles.'
        )


class PaginatedListMixin:
    """Standard pagination for every template-based list view in the
    project - students, courses, payments, results, invoices,
    departments, etc. Mix into a django.views.generic.ListView.

    Adds a ?per_page= override on top of Django's built-in paginate_by,
    clamped to a sane maximum so a user can't request an unbounded page
    and hammer the database.
    """

    paginate_by = 20
    max_paginate_by = 100
    page_size_query_param = 'per_page'

    def get_paginate_by(self, queryset):
        raw_value = self.request.GET.get(self.page_size_query_param)
        if not raw_value:
            return self.paginate_by
        try:
            size = int(raw_value)
        except (TypeError, ValueError):
            return self.paginate_by
        return max(1, min(size, self.max_paginate_by))
