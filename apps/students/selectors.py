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


def get_profile_completeness(student):
    """How much of the student's personal profile is filled in, and what
    is still missing - drives the dashboard prompt. Returns
    {'percent': int, 'missing': [labels], 'complete': bool}.
    """
    guardian = getattr(student, 'guardian', None)
    checks = [
        ('Profile picture', bool(student.user.avatar)),
        ('Date of birth', bool(student.date_of_birth)),
        ('Gender', bool(student.gender)),
        ('Home address', bool(student.home_address)),
        ('State of origin', bool(student.state_of_origin)),
        ('Phone number', bool(student.user.phone_number)),
        ("Guardian's name", bool(guardian and guardian.full_name)),
        ('Guardian relationship', bool(guardian and guardian.relationship)),
        ("Guardian's phone", bool(guardian and guardian.phone_number)),
        ("Guardian's address", bool(guardian and guardian.address)),
    ]
    missing = [label for label, done in checks if not done]
    return {
        'percent': round(100 * (len(checks) - len(missing)) / len(checks)),
        'missing': missing,
        'complete': not missing,
    }
