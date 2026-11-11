"""
Business logic for academic session/semester management.
"""
from django.core.exceptions import ValidationError

from .models import LevelSemesterState, Semester
from .models.level_state import DUPLICATE_MESSAGE


def set_level_semester(level, semester, programme=None):
    """Record a semester for a student level (FR-REG-02, per level:
    cohorts move at different paces, so each level is set independently).
    This is the only place level states should ever be written.

    A level may hold many semesters over time; adding one never replaces
    another. An exact duplicate of Programme + Level + Semester raises a
    ValidationError (the same rule the database constraint and the admin
    enforce). The level's current semester is the latest one - see
    selectors.get_semester_for_level.
    """
    if LevelSemesterState.objects.filter(level=level, programme=programme, semester=semester).exists():
        raise ValidationError(DUPLICATE_MESSAGE)
    return LevelSemesterState.objects.create(level=level, programme=programme, semester=semester)


def clear_level_semester(level, programme=None):
    """Remove the level's CURRENT semester - e.g. a mistake, or the
    Registrar closing a semester. Earlier semesters kept as history are
    untouched (the previous one becomes current). Returns the removed
    state, or None if the level had none.
    """
    from . import selectors

    scope = LevelSemesterState.objects.filter(level=level, programme=programme).select_related(
        'semester', 'semester__session',
    )
    current = selectors._latest(scope)
    if current:
        current.delete()
    return current


def set_registration_window(semester, *, start, end):
    semester.registration_start = start
    semester.registration_end = end
    semester.full_clean()
    semester.save(update_fields=['registration_start', 'registration_end', 'updated_at'])
    return semester


def archive_session(session):
    session.delete()
    return session


def restore_session(session):
    session.restore()
    return session


def archive_semester(semester):
    semester.delete()
    return semester


def restore_semester(semester):
    semester.restore()
    return semester
