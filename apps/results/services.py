"""
Business logic for grade entry, review, and publishing. This is the one
place the Grade status machine transitions - draft/rejected (lecturer
editable) -> submitted (locked, awaiting HOD) -> approved/rejected (HOD
decision) -> published (Exam Officer, visible to the student).
"""
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import Grade


def sync_grades_for_offering(course_offering):
    """Ensures every actively-registered student has a Grade row (Draft)
    for the lecturer to fill in. Safe to call repeatedly - only creates
    rows that don't already exist.
    """
    from apps.courses.models import CourseRegistration

    existing_ids = set(
        Grade.objects.filter(course_offering=course_offering).values_list('student_id', flat=True)
    )
    registered = CourseRegistration.objects.filter(
        course_offering=course_offering, status=CourseRegistration.Status.REGISTERED,
    ).exclude(student_id__in=existing_ids)

    Grade.objects.bulk_create([
        Grade(course_offering=course_offering, student=reg.student) for reg in registered
    ])


def submit_grades(course_offering):
    """Lecturer submits every editable (draft/rejected) grade for this
    offering at once - locking them for HOD review.
    """
    grades = Grade.objects.filter(
        course_offering=course_offering, status__in=[Grade.Status.DRAFT, Grade.Status.REJECTED],
    )
    return grades.update(status=Grade.Status.SUBMITTED, submitted_at=timezone.now())


def review_grade(grade, *, approve, reviewer, comment=''):
    """FR: only the HOD reviews lecturer-submitted grades."""
    if grade.status != Grade.Status.SUBMITTED:
        raise ValidationError('Only submitted grades can be reviewed.')

    grade.status = Grade.Status.APPROVED if approve else Grade.Status.REJECTED
    grade.reviewed_at = timezone.now()
    grade.reviewed_by = reviewer
    grade.review_comment = comment
    grade.save(update_fields=['status', 'reviewed_at', 'reviewed_by', 'review_comment', 'updated_at'])
    return grade


def publish_grades(course_offering):
    """FR: only the Exam Officer publishes results. Bulk-publishes every
    HOD-approved grade for the offering.
    """
    grades = Grade.objects.filter(course_offering=course_offering, status=Grade.Status.APPROVED)
    return grades.update(status=Grade.Status.PUBLISHED, published_at=timezone.now())


def unlock_grade(grade, *, comment=''):
    """FR-EXM-04: Exam Officer's rectification override - reopens a
    grade in ANY locked state (submitted, HOD-approved/rejected, or
    even already-published) back to Draft so the original lecturer can
    correct and resubmit it. Unlike the HOD's review_grade() reject,
    this works after the normal pipeline has already moved past HOD
    review, for errors/disputes caught later.
    """
    if grade.status == Grade.Status.DRAFT:
        raise ValidationError('This grade is already editable.')

    grade.status = Grade.Status.DRAFT
    grade.submitted_at = None
    grade.reviewed_at = None
    grade.reviewed_by = None
    grade.review_comment = comment
    grade.published_at = None
    grade.save(update_fields=[
        'status', 'submitted_at', 'reviewed_at', 'reviewed_by', 'review_comment', 'published_at', 'updated_at',
    ])
    return grade
