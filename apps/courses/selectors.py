"""
Read-only queries for the course catalog, course offerings, and
registrations.
"""
from django.db.models import Q

from .models import Course, CourseOffering, CourseRegistration


def get_course_list(*, search=None, department=None, level=None, include_archived=False):
    manager = Course.all_objects if include_archived else Course.objects
    qs = manager.select_related('department')

    if department:
        qs = qs.filter(department_id=department)

    if level:
        qs = qs.filter(level=level)

    if search:
        qs = qs.filter(Q(code__icontains=search) | Q(title__icontains=search))

    return qs


def get_offerings_for_department(department=None, *, semester=None, include_archived=False):
    """Used by the HOD screen - every offering for courses in their
    department, regardless of who's teaching (or not yet assigned).
    Passing department=None (Super Admin oversight) returns offerings
    across every department.
    """
    manager = CourseOffering.all_objects if include_archived else CourseOffering.objects
    qs = manager.select_related('course', 'semester', 'semester__session', 'lecturer', 'lecturer__user')
    if department:
        qs = qs.filter(course__department=department)
    if semester:
        qs = qs.filter(semester=semester)
    return qs


def get_available_offerings_for_student(student, semester):
    """FR-STU-05: offerings a student can register for - their own
    department AND level, the given semester, excluding ones they're
    already actively registered in (those show up under "My Courses"
    instead). A course is also available when either:
      - the student's own department/programme is explicitly listed in
        the course's eligible_departments/eligible_programmes (a course
        cross-listed to specific departments/programmes - e.g. a GST
        course shared by only a few departments), or
      - its department is flagged General Studies (open to every
        student college-wide) - but only as a fallback for courses that
        DON'T have an explicit eligible_departments/eligible_programmes
        list of their own. An HOD narrowing one specific GST course to a
        handful of departments/programmes should actually narrow it, not
        get overridden by the blanket "everyone" default.

    Within their own department, a student only sees courses that either
    have no Programme set (a general/unclassified department course) or
    whose Programme matches their own - a department like Community
    Health can run several programmes (CHEW, JCHEW, ...) with different
    curricula, so "in the department" alone isn't eligibility; a CHEW
    student shouldn't see or register for a JCHEW-only course just
    because both sit under the same department. If the STUDENT has no
    Programme assigned yet, this can't be enforced for them - they fall
    back to seeing every course in their department, same as before
    Programmes existed, until the Registrar assigns them one.

    Computed as two separate queries unioned by pk (rather than one query
    combining multiple M2M lookups with Q/~Q) to avoid Django's usual
    multi-valued-relationship join pitfalls.
    """
    registered_offering_ids = CourseRegistration.objects.filter(
        student=student, status=CourseRegistration.Status.REGISTERED,
    ).values_list('course_offering_id', flat=True)

    base_qs = CourseOffering.objects.filter(
        course__level=student.level, semester=semester,
    ).exclude(pk__in=registered_offering_ids)

    own_department = Q(course__department=student.department)
    if student.programme_id:
        own_department &= Q(course__programme__isnull=True) | Q(course__programme_id=student.programme_id)

    explicit_eligibility = own_department | Q(course__eligible_departments=student.department)
    if student.programme_id:
        explicit_eligibility |= Q(course__eligible_programmes=student.programme_id)
    explicit_ids = set(base_qs.filter(explicit_eligibility).values_list('pk', flat=True))

    blanket_ids = set(
        base_qs.filter(course__department__is_general_studies=True)
        .exclude(course__eligible_departments__isnull=False)
        .exclude(course__eligible_programmes__isnull=False)
        .values_list('pk', flat=True)
    )

    return base_qs.filter(pk__in=explicit_ids | blanket_ids).select_related(
        'course', 'lecturer', 'lecturer__user',
    )


def is_offering_eligible_for_student(course_offering, student):
    """Same eligibility rule as get_available_offerings_for_student,
    evaluated for one already-known offering rather than a queryset -
    used as a server-side check in services.register_course so a direct
    POST can't register a student for a course their programme, level,
    or department doesn't actually make them eligible for, regardless of
    what the "Available Courses" page happened to render.
    """
    course = course_offering.course

    if course.level != student.level:
        return False

    if course.department_id == student.department_id:
        if not student.programme_id or not course.programme_id or course.programme_id == student.programme_id:
            return True

    if course.eligible_departments.filter(pk=student.department_id).exists():
        return True

    if student.programme_id and course.eligible_programmes.filter(pk=student.programme_id).exists():
        return True

    if (
        course.department.is_general_studies
        and not course.eligible_departments.exists()
        and not course.eligible_programmes.exists()
    ):
        return True

    return False


def get_registered_courses(student, *, semester=None):
    qs = CourseRegistration.objects.filter(
        student=student, status=CourseRegistration.Status.REGISTERED,
    ).select_related('course_offering', 'course_offering__course', 'course_offering__semester', 'course_offering__semester__session')
    if semester:
        qs = qs.filter(course_offering__semester=semester)
    return qs


def get_class_list_for_offering(course_offering):
    """Every actively-registered student for one course offering - the
    lecturer's "class list".
    """
    return CourseRegistration.objects.filter(
        course_offering=course_offering, status=CourseRegistration.Status.REGISTERED,
    ).select_related('student', 'student__user').order_by('student__matric_number')


def get_department_course_tree(department, *, current_offerings_by_key=None):
    """Every course in a department, grouped Programme -> Level ->
    Semester, for the HOD dashboard and the course-allocation screen -
    replaces a flat course list with the structure the college actually
    plans around (FR: "HOD should see Programme first, Level, Semester
    then the Courses").

    Every level a programme runs (per Programme.duration_levels) and
    both semesters are always included, even with zero courses yet, so
    the tree reads as a skeleton to fill in rather than only showing
    what already exists - e.g. a 2-level Certificate always shows 100 &
    200 Level, never 300+.

    Courses with no Programme set (pre-existing data, or a course that
    deliberately isn't tied to one) are grouped under a trailing "No
    Programme" bucket instead of silently disappearing from the tree,
    covering only the levels that actually have such courses.

    ``current_offerings_by_key``, if given, is a ``{course_id: CourseOffering}``
    map (see get_current_offerings_for_department) used to annotate each
    course with ``.current_offering`` - the allocation screen uses this
    to show "Assign" vs. the already-assigned lecturer without a second
    query per course.
    """
    from apps.admissions.models import Programme
    from apps.core.constants import Level, SemesterName

    courses = list(
        Course.objects.filter(department=department).select_related('programme').order_by('code')
    )

    by_programme = {}
    no_programme_courses = []
    for course in courses:
        if current_offerings_by_key is not None:
            course.current_offering = current_offerings_by_key.get(course.id)
        if course.programme_id:
            by_programme.setdefault(course.programme_id, []).append(course)
        else:
            no_programme_courses.append(course)

    level_labels = dict(Level.choices)

    def build_levels(course_list, level_values):
        levels = []
        for level_value in level_values:
            level_courses = [c for c in course_list if c.level == level_value]
            semesters = [
                {
                    'value': sem_value,
                    'label': sem_label,
                    'courses': [c for c in level_courses if c.semester_name == sem_value],
                }
                for sem_value, sem_label in SemesterName.choices
            ]
            levels.append({'value': level_value, 'label': level_labels[level_value], 'semesters': semesters})
        return levels

    # Every active programme under the department is shown, not just
    # ones that already have a course - a freshly-created programme
    # still needs its empty Level/Semester skeleton visible so the HOD
    # has somewhere to start adding courses.
    programmes = Programme.objects.filter(department=department, is_active=True).order_by('name')
    tree = [
        {'programme': programme, 'levels': build_levels(by_programme.get(programme.pk, []), programme.levels)}
        for programme in programmes
    ]

    if no_programme_courses:
        present_levels = sorted({c.level for c in no_programme_courses})
        tree.append({'programme': None, 'levels': build_levels(no_programme_courses, present_levels)})

    return tree


def get_current_offerings_for_department(department):
    """{course_id: CourseOffering} for every course in the department that
    already has an offering in the semester currently running for its own
    level (per LevelSemesterState) - i.e. "has this course actually been
    allocated to a lecturer yet, for the semester it'd be allocated in
    right now". A course with no LevelSemesterState set for its level, or
    no offering yet, simply has no entry.
    """
    from apps.academics.selectors import get_level_semester_states

    semester_id_by_level = {
        state.level: state.semester_id for state in get_level_semester_states()
    }
    if not semester_id_by_level:
        return {}

    course_ids_by_level = {}
    for course in Course.objects.filter(department=department).values('id', 'level'):
        course_ids_by_level.setdefault(course['level'], []).append(course['id'])

    offerings_by_course_id = {}
    for level, semester_id in semester_id_by_level.items():
        course_ids = course_ids_by_level.get(level)
        if not course_ids:
            continue
        offerings = CourseOffering.objects.filter(
            course_id__in=course_ids, semester_id=semester_id,
        ).select_related('lecturer', 'lecturer__user')
        for offering in offerings:
            offerings_by_course_id[offering.course_id] = offering

    return offerings_by_course_id


def get_registrations_for_department(department=None, *, semester=None, status=None):
    """FR-HOD-06: every course registration for offerings in one
    department - the HOD's registration oversight queue. Passing
    department=None (Super Admin oversight) returns registrations
    across every department.
    """
    qs = CourseRegistration.objects.select_related(
        'student', 'student__user', 'course_offering', 'course_offering__course',
        'course_offering__semester', 'course_offering__semester__session',
    )
    if department:
        qs = qs.filter(course_offering__course__department=department)
    if semester:
        qs = qs.filter(course_offering__semester=semester)
    if status:
        qs = qs.filter(status=status)
    return qs.order_by('-created_at')


def get_cross_programme_registration_conflicts(*, department=None):
    """Diagnostic report: students actively registered under courses
    tagged with more than one distinct Programme within the same
    department - a person should only be on one programme (see
    is_offering_eligible_for_student), so this is almost always leftover
    from before Programmes existed, or from before the student had one
    assigned to their own record. Not auto-fixed here - staff need to
    look at each case and decide which registration is the mistake (drop
    it via the department's Course Registration Oversight screen, or
    Django admin), since there's no way to know that automatically.

    Passing department=None (Exam Officer/Registrar/Super Admin
    oversight) checks every department; a specific department scopes it
    to just that department's students, for the HOD view.
    """
    qs = CourseRegistration.objects.filter(
        status=CourseRegistration.Status.REGISTERED,
        course_offering__course__programme__isnull=False,
    ).select_related(
        'student', 'student__user', 'student__department',
        'course_offering__course__programme', 'course_offering__semester', 'course_offering__semester__session',
    )
    if department:
        qs = qs.filter(student__department=department)

    by_student = {}
    for reg in qs:
        by_student.setdefault(reg.student_id, {'student': reg.student, 'registrations': []})
        by_student[reg.student_id]['registrations'].append(reg)

    conflicts = []
    for entry in by_student.values():
        programmes = {reg.course_offering.course.programme for reg in entry['registrations']}
        if len(programmes) > 1:
            entry['programmes'] = sorted(programmes, key=lambda p: p.name)
            entry['registrations'].sort(key=lambda r: r.course_offering.course.code)
            conflicts.append(entry)

    conflicts.sort(key=lambda entry: entry['student'].matric_number)
    return conflicts
