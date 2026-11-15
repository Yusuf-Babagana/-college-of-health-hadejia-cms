"""
Business logic for student management: creating a student (User account
+ profile together) and status changes (FR-REG-05).
"""
from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Student


def create_student(*, first_name, last_name, email, matric_number, phone_number='', department, level,
                   admission_session, programme=None):
    """Provision a student: User account (role=student, temporary
    password) plus Student profile, atomically - a half-created student
    (account without profile) would be able to log in but see nothing.

    ``matric_number`` has no fixed format - it's whatever the Registrar
    was given/assigned, and only needs to be unique (enforced by the
    model field and, for a clearer form error, StudentCreateForm). The
    username is derived from it (lowercased, with '/' and spaces
    flattened to '.', since Django usernames can't contain those).
    Returns (student, temp_password); the password is shown exactly once
    by the caller.
    """
    from apps.accounts.models import User
    from apps.accounts.services import create_user
    from apps.core.constants import Role

    matric_number = matric_number.strip()
    if not matric_number:
        raise ValidationError({'matric_number': 'Matric number is required.'})

    # Matric number case is preserved (not forced uppercase - see
    # StudentCreateForm), but the username derived from it below is
    # always lowercased, so two matric numbers that differ only by case
    # (e.g. 'CHE/2025/0001' and 'che/2025/0001') would otherwise pass the
    # form's case-sensitive uniqueness check and only collide once
    # User.objects.create_user hits the DB - as an unhandled
    # IntegrityError instead of a clean form/validation error.
    username = matric_number.lower().replace('/', '.').replace(' ', '.')
    if User.objects.filter(username=username).exists():
        raise ValidationError(
            {'matric_number': 'A student with a matching matric number already exists.'}
        )

    with transaction.atomic():
        user, temp_password = create_user(
            username=username,
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


def next_level_for(student):
    """The level after the student's current one, within their programme's
    span (a 2-level certificate ends at 200). None if they're already at
    the final level.
    """
    from apps.core.constants import Level

    levels = student.programme.levels if student.programme_id else [value for value, _ in Level.choices]
    higher = [value for value in levels if value > student.level]
    return min(higher) if higher else None


def promote_student(student):
    """Move an active student up one level. Saves only the level, then
    re-reads it from the database so the caller reports what is really
    stored. The post_save signal in finance bills the new level's fees.
    Raises ValidationError if the student can't be promoted.
    """
    if student.status != Student.Status.ACTIVE:
        raise ValidationError(f'{student.matric_number} is {student.get_status_display().lower()}; only active students can be promoted.')
    new_level = next_level_for(student)
    if new_level is None:
        raise ValidationError(
            f'{student.matric_number} is already at the final level of their programme '
            f'({student.get_level_display()}); mark them Graduated instead.'
        )
    student.level = new_level
    student.save(update_fields=['level', 'updated_at'])
    student.refresh_from_db(fields=['level'])
    return student


def archive_student(student):
    student.delete()  # soft delete
    return student


def restore_student(student):
    student.restore()
    return student
