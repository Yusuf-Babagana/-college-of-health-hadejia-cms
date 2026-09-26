"""
Business logic for course catalog, course offering, and registration
management.
"""
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import CourseOffering, CourseRegistration, RegistrationApproval


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


def _create_registration(*, student, course_offering, bypass_locks, is_carryover=False):
    """Shared core of register_course/hod_register_course/
    register_carryover_course: financial clearance, capacity, no
    duplicates, and the FR-STU-06 max-credit-units-per-semester ceiling
    always apply. bypass_locks skips the registration-window and
    HOD-approval-lock checks, which only gate the student's own
    self-service registration - the HOD dashboard route
    (hod_register_course) is exactly how a course gets added once one or
    both of those has closed the self-service door. is_carryover relaxes
    only the level part of the eligibility gate - a carryover retake of a
    course the student already failed is legitimately outside their
    current level by definition (see FR-STU-CARRY), but department/
    programme eligibility still applies.
    """
    from apps.core.constants import MAX_CREDIT_UNITS_PER_SEMESTER
    from apps.finance.selectors import is_student_cleared

    from .selectors import get_registered_courses, is_offering_eligible_for_student, is_registration_approved

    semester = course_offering.semester
    subject = 'This student' if bypass_locks else 'You'

    if not bypass_locks:
        if not semester.is_registration_open:
            raise ValidationError('Course registration is not currently open for this semester.')

        if is_registration_approved(student, semester):
            raise ValidationError(
                'Your HOD has already approved your registration for this semester - '
                'contact your HOD to add a course now.'
            )

    # Defense in depth: "Available Courses" only ever renders eligible
    # offerings, but this is the one place that actually creates a
    # registration, so it has to re-check independently rather than
    # trusting whatever offering pk was posted - e.g. a JCHEW student
    # can't register for a CHEW-only course in the same department just
    # by knowing/guessing its URL.
    if not is_offering_eligible_for_student(course_offering, student, ignore_level=is_carryover):
        raise ValidationError(f'{subject} {"is" if bypass_locks else "are"} not eligible to register for this course.')

    if not is_student_cleared(student, semester.session):
        raise ValidationError(f'{subject} must clear outstanding fees before registering courses.')

    existing = CourseRegistration.objects.filter(student=student, course_offering=course_offering).first()
    if existing and existing.status == CourseRegistration.Status.REGISTERED:
        raise ValidationError(f'{subject} {"is" if bypass_locks else "are"} already registered for this course.')

    if course_offering.is_full:
        raise ValidationError('This course has reached its registration capacity.')

    current_units = sum(
        reg.course_offering.course.credit_units
        for reg in get_registered_courses(student, semester=semester).select_related('course_offering__course')
    )
    if current_units + course_offering.course.credit_units > MAX_CREDIT_UNITS_PER_SEMESTER:
        raise ValidationError(
            f'Registering {course_offering.course.code} would take {"this student" if bypass_locks else "you"} to '
            f'{current_units + course_offering.course.credit_units} credit units, over the '
            f'{MAX_CREDIT_UNITS_PER_SEMESTER}-unit maximum for one semester '
            f'(currently registered: {current_units} units).'
        )

    if existing:
        existing.status = CourseRegistration.Status.REGISTERED
        existing.save(update_fields=['status', 'updated_at'])
        return existing

    return CourseRegistration.objects.create(student=student, course_offering=course_offering)


def register_course(*, student, course_offering):
    return _create_registration(student=student, course_offering=course_offering, bypass_locks=False)


def hod_register_course(*, student, course_offering):
    """FR-HOD-07: once a student's registration is HOD-approved (or the
    registration window has closed), any further add has to go through
    the HOD dashboard instead of student self-service - this is that
    route. Eligibility, clearance, capacity, and the credit-unit ceiling
    still apply; only the window/approval-lock checks are skipped.
    """
    return _create_registration(student=student, course_offering=course_offering, bypass_locks=True)


def register_carryover_course(*, student, course_offering):
    """FR-STU-CARRY: registers a student for a freshly re-offered
    CourseOffering of a course they previously failed - see
    sync_carryover_registrations, which is what actually decides WHICH
    offering counts as "freshly re-offered" and calls this. Still
    respects the registration window and the HOD-approval lock like any
    self-service registration, and department/programme eligibility still
    applies; only the level part of the eligibility gate is relaxed,
    since a carryover is legitimately outside the student's current
    level by definition.
    """
    return _create_registration(student=student, course_offering=course_offering, bypass_locks=False, is_carryover=True)


def sync_carryover_registrations(student):
    """FR-STU-CARRY: "My Carryover" courses register themselves the
    moment they're re-offered, instead of the student having to remember
    to add them - e.g. a course failed in Level 100's First Semester is
    re-offered every session (a new intake takes it), which typically
    lines up calendar-wise with the student now being in Level 200's own
    First Semester. Called as a side effect of the student's normal
    registration screens (and the "My Carryover" page itself), so it has
    to be silent about anything it can't register yet (window closed, no
    fresh offering, already registered, not cleared, course full) rather
    than raise - those simply stay outstanding until the next visit.
    Returns the list of registrations it actually created/reactivated.
    """
    from apps.results.selectors import get_carryover_courses

    from .selectors import get_current_offering_for_course

    created = []
    for row in get_carryover_courses(student):
        offering = get_current_offering_for_course(row['course'])
        if not offering or offering.pk == row['failed_offering'].pk:
            continue
        if CourseRegistration.objects.filter(
            student=student, course_offering=offering, status=CourseRegistration.Status.REGISTERED,
        ).exists():
            continue
        try:
            created.append(register_carryover_course(student=student, course_offering=offering))
        except ValidationError:
            continue
    return created


def drop_course(*, student, course_offering):
    from .selectors import is_registration_approved

    semester = course_offering.semester
    if not semester.is_registration_open:
        raise ValidationError('Course registration is closed - courses can only be dropped during the registration window.')

    if is_registration_approved(student, semester):
        raise ValidationError(
            'Your HOD has already approved your registration for this semester - '
            'contact your HOD to drop a course now.'
        )

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
    """FR-HOD-06/07: departmental oversight override - the HOD can cancel
    a specific student's registration outside the normal self-service
    drop flow (e.g. the student shouldn't have been eligible for that
    course, or their registration is already approved), unlike
    drop_course() this isn't gated by the registration window or the
    approval lock.
    """
    if registration.status != CourseRegistration.Status.REGISTERED:
        raise ValidationError('Only active registrations can be cancelled.')

    registration.status = CourseRegistration.Status.DROPPED
    registration.save(update_fields=['status', 'updated_at'])
    return registration


def approve_registration(*, student, semester, reviewer, comment=''):
    """FR-HOD-07: the HOD signs off on a student's registration for one
    semester as a whole (not course-by-course). Once approved, the
    student's self-service add/drop locks, the registration slip becomes
    printable, and any further change routes through the HOD dashboard
    (hod_register_course / hod_cancel_registration).
    """
    from .selectors import get_registered_courses

    if not get_registered_courses(student, semester=semester).exists():
        raise ValidationError('This student has no active course registrations for this semester to approve.')

    approval, _ = RegistrationApproval.objects.get_or_create(student=student, semester=semester)
    if approval.status == RegistrationApproval.Status.APPROVED:
        raise ValidationError('This registration has already been approved.')

    approval.status = RegistrationApproval.Status.APPROVED
    approval.reviewed_at = timezone.now()
    approval.reviewed_by = reviewer
    approval.review_comment = comment
    approval.save(update_fields=['status', 'reviewed_at', 'reviewed_by', 'review_comment', 'updated_at'])
    return approval


def unapprove_registration(*, student, semester, reviewer, comment=''):
    """Reopens an already-approved registration for student self-service
    again - e.g. it was approved too early, or the student has a genuine
    correction the HOD would rather they make themselves.
    """
    approval = RegistrationApproval.objects.filter(student=student, semester=semester).first()
    if not approval or approval.status != RegistrationApproval.Status.APPROVED:
        raise ValidationError('This registration is not currently approved.')

    approval.status = RegistrationApproval.Status.PENDING
    approval.reviewed_at = timezone.now()
    approval.reviewed_by = reviewer
    approval.review_comment = comment
    approval.save(update_fields=['status', 'reviewed_at', 'reviewed_by', 'review_comment', 'updated_at'])
    return approval
