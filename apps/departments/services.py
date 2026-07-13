"""
Business logic for department management. Views stay thin and call these.
"""
from django.core.exceptions import ValidationError

from .models import Department


def _demote_if_no_longer_hod(lecturer):
    """Revert a lecturer's role back to Lecturer once they no longer head
    any department - unless they still head a different one.
    """
    from apps.core.constants import Role

    if lecturer.user.role == Role.HOD and not lecturer.headed_department.exists():
        lecturer.user.role = Role.LECTURER
        lecturer.user.save(update_fields=['role'])


def assign_hod(department, lecturer):
    """Assign lecturer as HOD of department. Enforced: the lecturer must
    already belong to this department (see Department.clean()).

    Also promotes the lecturer's User.role to HOD - without this, the
    dashboard redirect and RBAC permission groups (can_review_grades,
    can_approve_registration, can_assign_courses) would never apply to
    them, since those are all keyed off role, not off Department.hod.
    If someone else was previously HOD, they're demoted back to Lecturer
    (unless they still head a different department).
    """
    from apps.core.constants import Role

    if lecturer.department_id != department.pk:
        raise ValidationError('The selected lecturer does not belong to this department.')

    previous_hod = department.hod

    department.hod = lecturer
    department.full_clean()
    department.save(update_fields=['hod', 'updated_at'])

    if lecturer.user.role != Role.HOD:
        lecturer.user.role = Role.HOD
        lecturer.user.save(update_fields=['role'])

    if previous_hod and previous_hod.pk != lecturer.pk:
        _demote_if_no_longer_hod(previous_hod)

    return department


def remove_hod(department):
    previous_hod = department.hod
    department.hod = None
    department.save(update_fields=['hod', 'updated_at'])

    if previous_hod:
        _demote_if_no_longer_hod(previous_hod)

    return department


def archive_department(department):
    department.delete()  # soft delete, see apps.core.models.SoftDeleteModel
    return department


def restore_department(department):
    department.restore()
    return department
