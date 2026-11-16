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


PHOTO_SIZE = (480, 600)  # px, 4:5 portrait - passport proportions, plenty for a printed form


def update_profile_photo(user, uploaded_file):
    """Stores a student's profile picture: corrects phone-camera rotation,
    flattens transparency onto white, crops it to passport proportions
    (4:5, keeping the upper-middle so heads are not cut off) so it never
    looks stretched on the printed form, strips metadata (by re-encoding),
    saves it as JPEG under a random name and deletes the picture it
    replaces. Raises ValidationError if it isn't a real image.
    """
    import uuid
    from io import BytesIO

    from django.core.files.base import ContentFile
    from PIL import Image, ImageOps, UnidentifiedImageError

    try:
        image = ImageOps.exif_transpose(Image.open(uploaded_file))
        if image.mode in ('RGBA', 'LA', 'P'):
            image = image.convert('RGBA')
            flattened = Image.new('RGB', image.size, 'white')
            flattened.paste(image, mask=image.split()[-1])
            image = flattened
        else:
            image = image.convert('RGB')
        image = ImageOps.fit(image, PHOTO_SIZE, Image.LANCZOS, centering=(0.5, 0.3))
        buffer = BytesIO()
        image.save(buffer, 'JPEG', quality=88, optimize=True)
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise ValidationError('That file is not a valid image.')

    previous = user.avatar.name if user.avatar else ''
    user.avatar.save(f'{uuid.uuid4().hex}.jpg', ContentFile(buffer.getvalue()), save=True)
    if previous and previous != user.avatar.name:
        user.avatar.storage.delete(previous)
    return user


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


def classify_for_promotion(students):
    """Splits students into (movable, at_final_level, not_active) for a
    hand-picked selection (e.g. from the Django admin)."""
    movable, at_final, not_active = [], [], []
    for student in students:
        if student.is_deleted or student.status != Student.Status.ACTIVE:
            not_active.append(student)
        elif next_level_for(student) is None:
            at_final.append(student)
        else:
            movable.append(student)
    return movable, at_final, not_active


def promote_many(students):
    """Promotes a selection of students one level each, all or nothing.
    Inactive/archived students and those at their programme's final level
    are left unchanged. Returns (promoted, at_final_level, not_active)."""
    movable, at_final, not_active = classify_for_promotion(students)
    with transaction.atomic():
        for student in movable:
            student.level = next_level_for(student)
            student.save(update_fields=['level', 'updated_at'])  # finance signal bills the new level
    return len(movable), len(at_final), len(not_active)


def _promotable_students(level, programme=None):
    students = Student.objects.filter(status=Student.Status.ACTIVE, level=level).select_related('programme')
    if programme is not None:
        students = students.filter(programme=programme)
    return students


def preview_bulk_promotion(*, level, programme=None):
    """(will_be_promoted, at_final_level) for the active students of a
    level (optionally one programme) - what promote_students would do."""
    will_promote = at_final = 0
    for student in _promotable_students(level, programme):
        if next_level_for(student) is None:
            at_final += 1
        else:
            will_promote += 1
    return will_promote, at_final


def promote_students(*, level, programme=None):
    """Bulk promotion: moves every active student at ``level`` (optionally
    only one programme) up one level, all or nothing. Students already at
    their programme's final level are left alone - they should be marked
    Graduated, not promoted. Returns (promoted, skipped_at_final_level).
    """
    promoted = skipped = 0
    with transaction.atomic():
        for student in _promotable_students(level, programme):
            new_level = next_level_for(student)
            if new_level is None:
                skipped += 1
                continue
            student.level = new_level
            student.save(update_fields=['level', 'updated_at'])  # finance signal bills the new level
            promoted += 1
    return promoted, skipped


def archive_student(student):
    student.delete()  # soft delete
    return student


def restore_student(student):
    student.restore()
    return student
