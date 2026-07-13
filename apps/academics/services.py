"""
Business logic for academic session/semester management.
"""
from .models import LevelSemesterState, Semester


def set_level_semester(level, semester):
    """Point a student level at its current semester (FR-REG-02, per
    level: cohorts move at different paces, so each level's current
    semester is set independently). This is the only place level states
    should ever be written.
    """
    state, _ = LevelSemesterState.objects.update_or_create(
        level=level, defaults={'semester': semester},
    )
    return state


def clear_level_semester(level):
    """Put a level into a "no semester in progress" state - e.g. between
    sessions, before the Registrar opens the next one for that level.
    """
    LevelSemesterState.objects.filter(level=level).delete()


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
