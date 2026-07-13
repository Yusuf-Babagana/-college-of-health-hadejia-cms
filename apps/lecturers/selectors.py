"""
Read-only queries for lecturer profiles.
"""
from django.db.models import Q

from .models import Lecturer


def get_lecturer_list(*, search=None, department=None, include_archived=False):
    manager = Lecturer.all_objects if include_archived else Lecturer.objects
    qs = manager.select_related('user', 'department')

    if department:
        qs = qs.filter(department_id=department)

    if search:
        qs = qs.filter(
            Q(user__username__icontains=search)
            | Q(user__first_name__icontains=search)
            | Q(user__last_name__icontains=search)
            | Q(qualification__icontains=search)
        )

    return qs


def get_lecturer_role_users_without_profile(*, exclude_user=None):
    """Users with role=lecturer who don't already have a Lecturer profile -
    the only valid choices when creating a new profile.
    """
    from apps.accounts.models import User
    from apps.core.constants import Role

    qs = User.objects.filter(role=Role.LECTURER, lecturer_profile__isnull=True)
    if exclude_user:
        qs = qs | User.objects.filter(pk=exclude_user.pk)
    return qs
