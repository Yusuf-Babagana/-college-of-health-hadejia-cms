"""
Read-only queries for academic sessions, semesters, and level states.
"""
from .models import AcademicSession, LevelSemesterState, Semester


def get_session_list(*, search=None, include_archived=False):
    manager = AcademicSession.all_objects if include_archived else AcademicSession.objects
    qs = manager.all()
    if search:
        qs = qs.filter(name__icontains=search)
    return qs


def get_active_sessions():
    """For dropdowns elsewhere (semester form, student admission form)."""
    return AcademicSession.objects.all()


def get_semester_list(*, session=None, include_archived=False):
    manager = Semester.all_objects if include_archived else Semester.objects
    qs = manager.select_related('session')
    if session:
        qs = qs.filter(session_id=session)
    return qs


def get_semester_for_level(level):
    """The semester a given student level is currently running, or None
    if the Registrar hasn't opened one for that level. This replaces the
    old single global "active semester" - a student's (or course's)
    current semester is always resolved through their level.
    """
    state = (
        LevelSemesterState.objects.filter(level=level)
        .select_related('semester', 'semester__session')
        .first()
    )
    return state.semester if state else None


def get_level_semester_states():
    """Every level's current semester, for the Registrar's level-state
    screen and staff dashboards."""
    return LevelSemesterState.objects.select_related('semester', 'semester__session').order_by('level')


def get_current_semesters():
    """The distinct semesters currently running for at least one level -
    for views without a single-level context (lecturer workload, results
    fallbacks), where "current" means current for any level.
    """
    semester_ids = LevelSemesterState.objects.values_list('semester_id', flat=True)
    return Semester.objects.filter(pk__in=semester_ids).select_related('session')


def get_current_sessions():
    """The distinct sessions with a semester in progress for at least
    one level, newest first. Usually a single session, but two when
    cohorts straddle a session boundary - money/report views should
    aggregate over all of them rather than silently dropping one.
    """
    session_ids = get_current_semesters().values_list('session_id', flat=True)
    return AcademicSession.objects.filter(pk__in=session_ids).order_by('-name')


def get_current_session():
    """The most recent session with a semester in progress for some
    level. Most of the time every level is in the same session; when
    cohorts straddle two sessions this returns the newer one, and
    per-student figures should resolve through the student's level
    instead (get_semester_for_level).
    """
    return get_current_sessions().first()
