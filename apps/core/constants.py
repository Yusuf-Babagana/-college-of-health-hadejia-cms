"""
System-wide constants shared across apps.
"""
from django.db import models


class Level(models.IntegerChoices):
    """Student academic levels, shared across students/courses/academics."""
    LEVEL_100 = 100, '100 Level'
    LEVEL_200 = 200, '200 Level'
    LEVEL_300 = 300, '300 Level'
    LEVEL_400 = 400, '400 Level'
    LEVEL_500 = 500, '500 Level'
    LEVEL_600 = 600, '600 Level'


class SemesterName(models.TextChoices):
    """Shared between academics.Semester (a semester within a session)
    and courses.Course (which semester a catalog course is normally
    taught in), so a course's declared semester and an offering's actual
    semester can be compared directly.
    """
    FIRST = 'first', 'First Semester'
    SECOND = 'second', 'Second Semester'


# FR-STU-06: the hard ceiling on how many credit units a student may
# carry in a single semester, regardless of how many offerings are open.
MAX_CREDIT_UNITS_PER_SEMESTER = 24


class Role(models.TextChoices):
    """Canonical set of user roles used for RBAC across the system."""
    STUDENT = 'student', 'Student'
    LECTURER = 'lecturer', 'Lecturer'
    HOD = 'hod', 'Head of Department'
    REGISTRAR = 'registrar', 'Registrar'
    BURSAR = 'bursar', 'Bursar'
    EXAM_OFFICER = 'exam_officer', 'Exam Officer'
    PRACTICAL_COORD = 'practical_coord', 'Practical Coordinator'
    ICT_ADMIN = 'ict_admin', 'ICT Administrator'
    SUPER_ADMIN = 'super_admin', 'Super Administrator'
    APPLICANT = 'applicant', 'Applicant'


# Roles that are considered "staff" for Django admin/staff-area access.
STAFF_ROLES = (
    Role.LECTURER,
    Role.HOD,
    Role.REGISTRAR,
    Role.BURSAR,
    Role.EXAM_OFFICER,
    Role.PRACTICAL_COORD,
    Role.ICT_ADMIN,
    Role.SUPER_ADMIN,
)

# Maps each role to the URL name of its dashboard landing page.
ROLE_DASHBOARD_URL_NAMES = {
    Role.STUDENT: 'dashboard:student',
    Role.LECTURER: 'dashboard:lecturer',
    Role.HOD: 'dashboard:hod',
    Role.REGISTRAR: 'dashboard:registrar',
    Role.BURSAR: 'dashboard:bursar',
    Role.EXAM_OFFICER: 'dashboard:exam_officer',
    Role.PRACTICAL_COORD: 'dashboard:practical_coordinator',
    Role.ICT_ADMIN: 'dashboard:ict_admin',
    Role.SUPER_ADMIN: 'dashboard:super_admin',
    Role.APPLICANT: 'admissions:dashboard',
}

# Maps each role to the custom (non-CRUD) permission codenames its group
# should hold by default, straight from the master plan's Business Rules
# (e.g. "Only Exam Officer publishes results"). Defined in apps.core.models
# on GlobalPermission. ICT Admin and Super Admin are intentionally left
# out here - they operate through is_staff/is_superuser and Django admin,
# not through these business-action permissions.
ROLE_PERMISSIONS = {
    Role.HOD: (
        'core.can_assign_courses',
        'core.can_approve_registration',
        'core.can_review_grades',
    ),
    Role.BURSAR: (
        'core.can_verify_payment',
    ),
    Role.EXAM_OFFICER: (
        'core.can_compile_results',
        'core.can_publish_results',
        'core.can_generate_transcript',
    ),
    Role.REGISTRAR: (
        'core.can_approve_admission',
        'core.can_generate_matric_numbers',
        'core.can_activate_semester',
    ),
}
