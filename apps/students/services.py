"""
Business logic for student management: creating a student (User account
+ profile together, with an auto-generated matric number) and status
changes (FR-REG-05).
"""
from django.db import transaction
from django.db.models.functions import Length

from .models import Student


def _next_matric_number(department, admission_session):
    """First free matric number for this department + admission year,
    e.g. CHE/2025/0005. Sequences never reuse a number: the next one is
    max(existing) + 1, so an archived or deleted student's number stays
    retired.
    """
    from apps.core.utils.generators import generate_matric_number

    admission_year = int(admission_session.name.partition('/')[0])
    prefix = f'{department.code}/{admission_year}/'

    last = (
        Student.all_objects.filter(matric_number__startswith=prefix)
        .order_by(Length('matric_number').desc(), '-matric_number')
        .values_list('matric_number', flat=True)
        .first()
    )
    last_sequence = 0
    if last:
        suffix = last.removeprefix(prefix)
        if suffix.isdigit():
            last_sequence = int(suffix)

    return generate_matric_number(department.code, admission_year, last_sequence + 1)


def create_student(*, first_name, last_name, email, phone_number='', department, level,
                   admission_session, matric_number='', programme=None):
    """Provision a student: User account (role=student, temporary
    password) plus Student profile, atomically - a half-created student
    (account without profile) would be able to log in but see nothing.

    ``matric_number`` may be supplied (e.g. a transfer student keeping an
    existing number); when blank the next number in the department +
    admission-year sequence is generated. The username is the matric
    number with '/' flattened to '.', since Django usernames can't
    contain slashes. Returns (student, temp_password); the password is
    shown exactly once by the caller.
    """
    from apps.accounts.services import create_user
    from apps.core.constants import Role

    with transaction.atomic():
        matric_number = matric_number.strip().upper() or _next_matric_number(department, admission_session)
        user, temp_password = create_user(
            username=matric_number.lower().replace('/', '.'),
            email=email,
            first_name=first_name,
            last_name=last_name,
            role=Role.STUDENT,
            phone_number=phone_number,
        )
        student = Student(
            user=user,
            matric_number=matric_number,
            department=department,
            programme=programme,
            level=level,
            admission_session=admission_session,
        )
        student.full_clean()
        student.save()
    return student, temp_password


def update_student_status(student, new_status):
    """Change a student's academic status. Per FR-REG-05, status dictates
    portal access: anything other than Active blocks login (checked via
    is_active_account, same mechanism as ICT Admin's user deactivation),
    and Active restores it.
    """
    student.status = new_status
    student.save(update_fields=['status', 'updated_at'])

    should_have_access = new_status == Student.Status.ACTIVE
    if student.user.is_active_account != should_have_access:
        student.user.is_active_account = should_have_access
        student.user.save(update_fields=['is_active_account'])

    return student


def archive_student(student):
    student.delete()  # soft delete
    return student


def restore_student(student):
    student.restore()
    return student
