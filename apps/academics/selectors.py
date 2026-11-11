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


def _recency_key(state):
    """Ordering for "which of a scope's states is current": the newest
    session wins, then the later semester within it (Second over First)."""
    return (state.semester.session.name, state.semester.name)


def _latest(states):
    return max(states, key=_recency_key, default=None)


def get_semester_for_level(level, programme=None):
    """The semester a given student level is currently running, or None
    if the Registrar hasn't opened one for that level. This replaces the
    old single global "active semester" - a student's (or course's)
    current semester is always resolved through their level.

    A level can hold several states over time (one per semester); the
    current one is the latest by session then semester.

    Pass ``programme`` (a Programme or its pk) to honour a
    programme-specific state; with none set - or no programme given -
    the college-wide default (programme NULL) applies.
    """
    states = list(
        LevelSemesterState.objects.filter(level=level).select_related('semester', 'semester__session')
    )
    programme_id = getattr(programme, 'pk', programme)
    if programme_id:
        state = _latest(s for s in states if s.programme_id == programme_id)
        if state:
            return state.semester
    state = _latest(s for s in states if s.programme_id is None)
    return state.semester if state else None


def _current_state_ids():
    """pks of the current state per (programme, level) scope."""
    latest = {}
    for state in LevelSemesterState.objects.select_related('semester', 'semester__session'):
        key = (state.programme_id, state.level)
        if key not in latest or _recency_key(state) > _recency_key(latest[key]):
            latest[key] = state
    return [state.pk for state in latest.values()]


def get_level_semester_states():
    """Every level's CURRENT state (one per programme + level scope), for
    the Registrar's level-state screen and staff dashboards. Older
    semesters kept as history are excluded - see get_level_state_history."""
    return LevelSemesterState.objects.filter(pk__in=_current_state_ids()).select_related(
        'semester', 'semester__session', 'programme',
    ).order_by('level', 'programme__name')


def get_level_state_history():
    """Every state row, current and past."""
    return LevelSemesterState.objects.select_related(
        'semester', 'semester__session', 'programme',
    ).order_by('level', 'programme__name', '-semester__session__name', '-semester__name')


def get_active_programmes():
    """Programmes offered in the Program -> Level -> Semester-Session
    selector. Deliberately NOT routed through programme.department,
    which is NULL on every existing row."""
    from apps.admissions.models import Programme

    return Programme.objects.filter(is_active=True).order_by('name')


def get_levels_for_programme(programme):
    """[(value, label)] for the levels a programme spans (100 up to
    duration_levels x 100)."""
    from apps.core.constants import Level

    labels = dict(Level.choices)
    return [(value, labels[value]) for value in programme.levels]


def get_semesters_for_selection():
    """Semester-Session combinations available to every programme/level
    (semesters are global today), newest session first."""
    return Semester.objects.select_related('session')


def get_current_semesters():
    """The distinct semesters currently running for at least one level -
    for views without a single-level context (lecturer workload, results
    fallbacks), where "current" means current for any level.
    """
    semester_ids = LevelSemesterState.objects.filter(pk__in=_current_state_ids()).values_list('semester_id', flat=True)
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
