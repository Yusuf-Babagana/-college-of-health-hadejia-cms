"""
Read-only queries for user accounts. Views call these instead of building
querysets inline.
"""
from django.db.models import Q

from .models import User


def get_user_list(*, search=None, role=None):
    """Users for the ICT Admin user-management screen, newest first."""
    qs = User.objects.all()

    if role:
        qs = qs.filter(role=role)

    if search:
        qs = qs.filter(
            Q(username__icontains=search)
            | Q(email__icontains=search)
            | Q(first_name__icontains=search)
            | Q(last_name__icontains=search)
        )

    return qs.order_by('-date_joined')
