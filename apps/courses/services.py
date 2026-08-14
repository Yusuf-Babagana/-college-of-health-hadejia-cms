"""
Business logic for course catalog, course offering, and registration
management.
"""
from django.core.exceptions import ValidationError

from .models import CourseOffering, CourseRegistration


def archive_course(course):
    course.delete()  # soft delete
    return course


def restore_course(course):
    course.restore()
    return course


def create_course_offering(*, course, semester, lecturer=None, capacity):
    offering = CourseOffering(course=course, semester=semester, lecturer=lecturer, capacity=capacity)
    offering.full_clean()
    offering.save()
    return offering


def update_course_offering(offering, *, lecturer, capacity):
    offering.lecturer = lecturer
    offering.capacity = capacity
    offering.full_clean()
    offering.save(update_fields=['lecturer', 'capacity', 'updated_at'])
    return offering


def archive_course_offering(offering):
    offering.delete()
    return offering


def restore_course_offering(offering):
    offering.restore()
    return offering


def register_course(*, student, course_offering):
    """Enforces every FR-COURSE-REG business rule in one place: open
    registration window, financial clearance, capacity, no duplicates,
    and the FR-STU-06 max-credit-units-per-semester ceiling.
    """
    from apps.core.constants import MAX_CREDIT_UNITS_PER_SEMESTER
    from apps.finance.selectors import is_student_cleared

    from .selectors import get_registered_courses, is_offering_eligible_for_student

    semester = course_offering.semester

    if not semester.is_registration_open:
        raise ValidationError('Course registration is not currently open for this semester.')

    # Defense in depth: "Available Courses" only ever renders eligible
    # offerings, but this is the one place that actually creates a
    # registration, so it has to re-check independently rather than
    # trusting whatever offering pk was posted - e.g. a JCHEW student
    # can't register for a CHEW-only course in the same department just
    # by knowing/guessing its URL.
    if not is_offering_eligible_for_student(course_offering, student):
        raise ValidationError('You are not eligible to register for this course.')

    if not is_student_cleared(student, semester.session):
        raise ValidationError('You must clear your outstanding fees before registering courses.')

    existing = CourseRegistration.objects.filter(student=student, course_offering=course_offering).first()
    if existing and existing.status == CourseRegistration.Status.REGISTERED:
        raise ValidationError('You are already registered for this course.')

    if course_offering.is_full:
        raise ValidationError('This course has reached its registration capacity.')

    current_units = sum(
        reg.course_offering.course.credit_units
        for reg in get_registered_courses(student, semester=semester).select_related('course_offering__course')
    )
    if current_units + course_offering.course.credit_units > MAX_CREDIT_UNITS_PER_SEMESTER:
        raise ValidationError(
            f'Registering {course_offering.course.code} would take you to '
            f'{current_units + course_offering.course.credit_units} credit units, over the '
            f'{MAX_CREDIT_UNITS_PER_SEMESTER}-unit maximum for one semester '
            f'(currently registered: {current_units} units).'
        )

    if existing:
        existing.status = CourseRegistration.Status.REGISTERED
        existing.save(update_fields=['status', 'updated_at'])
        return existing

    return CourseRegistration.objects.create(student=student, course_offering=course_offering)


def drop_course(*, student, course_offering):
    semester = course_offering.semester
    if not semester.is_registration_open:
        raise ValidationError('Course registration is closed - courses can only be dropped during the registration window.')

    try:
        registration = CourseRegistration.objects.get(
            student=student, course_offering=course_offering, status=CourseRegistration.Status.REGISTERED,
        )
    except CourseRegistration.DoesNotExist:
        raise ValidationError('You are not registered for this course.')

    registration.status = CourseRegistration.Status.DROPPED
    registration.save(update_fields=['status', 'updated_at'])
    return registration


def hod_cancel_registration(registration):
    """FR-HOD-06: departmental oversight override - the HOD can cancel a
    specific student's registration outside the normal self-service drop
    flow (e.g. the student shouldn't have been eligible for that course),
    unlike drop_course() this isn't gated by the registration window.
    """
    if registration.status != CourseRegistration.Status.REGISTERED:
        raise ValidationError('Only active registrations can be cancelled.')

    registration.status = CourseRegistration.Status.DROPPED
    registration.save(update_fields=['status', 'updated_at'])
    return registration
