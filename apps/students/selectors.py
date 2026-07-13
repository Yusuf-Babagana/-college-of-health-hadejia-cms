"""
Read-only queries for the student directory (FR-REG-06).
"""
from django.db.models import Q

from .models import Student


def get_student_list(*, search=None, department=None, level=None, status=None, include_archived=False):
    manager = Student.all_objects if include_archived else Student.objects
    qs = manager.select_related('user', 'department', 'admission_session')

    if department:
        qs = qs.filter(department_id=department)

    if level:
        qs = qs.filter(level=level)

    if status:
        qs = qs.filter(status=status)

    if search:
        qs = qs.filter(
            Q(matric_number__icontains=search)
            | Q(user__first_name__icontains=search)
            | Q(user__last_name__icontains=search)
            | Q(user__username__icontains=search)
        )

    return qs
