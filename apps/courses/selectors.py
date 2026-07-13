"""
Read-only queries for the course catalog, course offerings, and
registrations.
"""
from django.db.models import Q

from .models import Course, CourseOffering, CourseRegistration


def get_course_list(*, search=None, department=None, level=None, include_archived=False):
    manager = Course.all_objects if include_archived else Course.objects
    qs = manager.select_related('department')

    if department:
        qs = qs.filter(department_id=department)

    if level:
        qs = qs.filter(level=level)

    if search:
        qs = qs.filter(Q(code__icontains=search) | Q(title__icontains=search))

    return qs


def get_offerings_for_department(department=None, *, semester=None, include_archived=False):
    """Used by the HOD screen - every offering for courses in their
    department, regardless of who's teaching (or not yet assigned).
    Passing department=None (Super Admin oversight) returns offerings
    across every department.
    """
    manager = CourseOffering.all_objects if include_archived else CourseOffering.objects
    qs = manager.select_related('course', 'semester', 'semester__session', 'lecturer', 'lecturer__user')
    if department:
        qs = qs.filter(course__department=department)
    if semester:
        qs = qs.filter(semester=semester)
    return qs


def get_available_offerings_for_student(student, semester):
    """FR-STU-05: offerings a student can register for - their own
    department AND level, the given semester, excluding ones they're
    already actively registered in (those show up under "My Courses"
    instead).
    """
    registered_offering_ids = CourseRegistration.objects.filter(
        student=student, status=CourseRegistration.Status.REGISTERED,
    ).values_list('course_offering_id', flat=True)

    return CourseOffering.objects.filter(
        course__department=student.department, course__level=student.level, semester=semester,
    ).exclude(pk__in=registered_offering_ids).select_related('course', 'lecturer', 'lecturer__user')


def get_registered_courses(student, *, semester=None):
    qs = CourseRegistration.objects.filter(
        student=student, status=CourseRegistration.Status.REGISTERED,
    ).select_related('course_offering', 'course_offering__course', 'course_offering__semester', 'course_offering__semester__session')
    if semester:
        qs = qs.filter(course_offering__semester=semester)
    return qs


def get_class_list_for_offering(course_offering):
    """Every actively-registered student for one course offering - the
    lecturer's "class list".
    """
    return CourseRegistration.objects.filter(
        course_offering=course_offering, status=CourseRegistration.Status.REGISTERED,
    ).select_related('student', 'student__user').order_by('student__matric_number')


def get_registrations_for_department(department=None, *, semester=None, status=None):
    """FR-HOD-06: every course registration for offerings in one
    department - the HOD's registration oversight queue. Passing
    department=None (Super Admin oversight) returns registrations
    across every department.
    """
    qs = CourseRegistration.objects.select_related(
        'student', 'student__user', 'course_offering', 'course_offering__course',
        'course_offering__semester', 'course_offering__semester__session',
    )
    if department:
        qs = qs.filter(course_offering__course__department=department)
    if semester:
        qs = qs.filter(course_offering__semester=semester)
    if status:
        qs = qs.filter(status=status)
    return qs.order_by('-created_at')
