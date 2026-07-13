"""
Read-only queries for departments.
"""
from .models import Department


def get_department_list(*, search=None, include_archived=False):
    manager = Department.all_objects if include_archived else Department.objects
    qs = manager.select_related('hod', 'hod__user')
    if search:
        from django.db.models import Q
        qs = qs.filter(Q(name__icontains=search) | Q(code__icontains=search))
    return qs


def get_active_departments():
    """Used to populate dropdowns elsewhere (lecturer/course forms)."""
    return Department.objects.all()


def get_eligible_hod_choices(department):
    """Lecturers who already belong to this department - the only valid
    HOD candidates, per Department.clean()'s business rule.
    """
    from apps.lecturers.models import Lecturer
    return Lecturer.objects.filter(department=department).select_related('user')
