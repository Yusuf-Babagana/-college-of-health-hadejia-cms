"""
Read-only queries for grade bands, grade entry queues, review queues,
and published results/GPA.
"""
from .models import Grade, GradeBand

# FR-EXM-06: Master Broadsheet remark cutoffs, on this college's 4-point
# semester-GPA scale (confirmed by the user 2026-09-26) - anyone below
# LOWER_CREDIT_GPA, or with any Fail this semester regardless of GPA, is
# remarked Fail. REMARK_ORDER is the row-sort key: passing remarks first
# (best to worst), Pending (no grades yet) next, Fail rows sink to the
# bottom of the sheet.
DISTINCTION_GPA = 3.50
UPPER_CREDIT_GPA = 3.00
LOWER_CREDIT_GPA = 2.00
REMARK_ORDER = {'Distinction': 0, 'Upper Credit': 1, 'Lower Credit': 2, 'Pending': 3, 'Fail': 4}


def get_grade_bands():
    return GradeBand.objects.select_related('department', 'programme').all()


def compute_broadsheet_remark(gpa, *, has_fail):
    """FR-EXM-06: the Master Broadsheet's Remark column - 'Pending' when
    the student has no graded courses yet (never Fail just for being
    ungraded), 'Fail' for any outstanding Fail this semester or a GPA
    below LOWER_CREDIT_GPA, otherwise the matching pass tier.
    """
    if gpa is None:
        return 'Pending'
    if has_fail or gpa < LOWER_CREDIT_GPA:
        return 'Fail'
    if gpa >= DISTINCTION_GPA:
        return 'Distinction'
    if gpa >= UPPER_CREDIT_GPA:
        return 'Upper Credit'
    return 'Lower Credit'


def get_offerings_for_lecturer(lecturer, *, semester=None):
    from apps.courses.models import CourseOffering

    qs = CourseOffering.objects.filter(lecturer=lecturer).select_related(
        'course', 'semester', 'semester__session',
    )
    if semester:
        qs = qs.filter(semester=semester)
    return qs.order_by('-semester__session__name', 'course__code')


def get_grades_for_offering(course_offering):
    return Grade.objects.filter(course_offering=course_offering).select_related('student', 'student__user')


def get_submitted_grades_for_department(department=None, *, semester=None):
    """Passing department=None (Super Admin oversight) returns submitted
    grades across every department.
    """
    qs = Grade.objects.filter(status=Grade.Status.SUBMITTED).select_related(
        'student', 'student__user', 'course_offering', 'course_offering__course', 'course_offering__semester',
    )
    if department:
        qs = qs.filter(course_offering__course__department=department)
    if semester:
        qs = qs.filter(course_offering__semester=semester)
    return qs


def get_approved_grades(*, department=None, semester=None):
    qs = Grade.objects.filter(status=Grade.Status.APPROVED).select_related(
        'student', 'student__user', 'course_offering', 'course_offering__course', 'course_offering__semester',
    )
    if department:
        qs = qs.filter(course_offering__course__department=department)
    if semester:
        qs = qs.filter(course_offering__semester=semester)
    return qs


def get_published_results_for_student(student, *, semester=None):
    qs = Grade.objects.filter(student=student, status=Grade.Status.PUBLISHED).select_related(
        'course_offering', 'course_offering__course', 'course_offering__semester', 'course_offering__semester__session',
    )
    if semester:
        qs = qs.filter(course_offering__semester=semester)
    return qs


def get_carryover_courses(student):
    """FR-STU-CARRY: courses still outstanding as a Fail - i.e. the
    student's most recent PUBLISHED attempt at that course was a Fail,
    not cleared by any later retake. A course can be attempted more than
    once across different CourseOfferings (each retake is a new Grade
    row against a new CourseOffering of the same Course - Grade is only
    unique per (student, course_offering), not per (student, course)),
    so this groups by Course and looks only at the LATEST attempt,
    ordering attempts by (session name, semester name) - safe here since
    session names are "YYYY/YYYY" and semester names are "first"/
    "second", both of which sort correctly as plain strings (the same
    assumption Semester.Meta.ordering already relies on).

    Pass/fail isn't a stored field - Grade.letter_grade resolves it live
    against GradeBand, scoped to this student's own department/programme
    (see GradeBand's docstring) - each grade's ``student`` is set to the
    already-loaded instance passed in here, so that lookup doesn't issue
    a redundant query per grade just to re-fetch the student it already
    came from.

    Returns a list of {'course', 'failed_grade', 'failed_offering'}
    dicts, sorted by course code.
    """
    latest_by_course = {}
    for grade in get_published_results_for_student(student):
        grade.student = student
        course = grade.course_offering.course
        sort_key = (grade.course_offering.semester.session.name, grade.course_offering.semester.name)
        latest = latest_by_course.get(course.id)
        if latest is None or sort_key > latest['sort_key']:
            latest_by_course[course.id] = {'course': course, 'grade': grade, 'sort_key': sort_key}

    rows = [
        {'course': entry['course'], 'failed_grade': entry['grade'], 'failed_offering': entry['grade'].course_offering}
        for entry in latest_by_course.values()
        if entry['grade'].letter_grade == 'F'
    ]
    rows.sort(key=lambda row: row['course'].code)
    return rows


def get_score_sheet_for_student(student, *, semester=None):
    """FR: every course a student is registered for, with their CA1/CA2
    scores exactly as the lecturer has saved them so far - regardless of
    Grade.status. Unlike published results, this is live: a score shows
    up the moment a lecturer saves it in Grade Entry, even in Draft.
    Exam score and letter grade are deliberately left out - those stay
    behind the normal publish gate.
    """
    from apps.courses.models import CourseRegistration

    registrations = CourseRegistration.objects.filter(
        student=student, status=CourseRegistration.Status.REGISTERED,
    ).select_related(
        'course_offering', 'course_offering__course',
        'course_offering__semester', 'course_offering__semester__session',
    ).order_by('-course_offering__semester__session__name', 'course_offering__course__code')

    if semester:
        registrations = registrations.filter(course_offering__semester=semester)

    grades_by_offering = {
        grade.course_offering_id: grade
        for grade in Grade.objects.filter(
            student=student,
            course_offering_id__in=[reg.course_offering_id for reg in registrations],
        )
    }

    return [
        {'course_offering': reg.course_offering, 'grade': grades_by_offering.get(reg.course_offering_id)}
        for reg in registrations
    ]


def _weighted_average(grades):
    total_points = 0.0
    total_units = 0
    for grade in grades:
        point = grade.grade_point
        if point is None:
            continue
        units = grade.course_offering.course.credit_units
        total_points += float(point) * units
        total_units += units
    return round(total_points / total_units, 2) if total_units else None


def compute_gpa(student, semester):
    """Grade-point weighted average for one semester's published grades."""
    grades = get_published_results_for_student(student, semester=semester).select_related('course_offering__course')
    return _weighted_average(grades)


def compute_cgpa(student):
    """Grade-point weighted average across every published grade ever."""
    grades = Grade.objects.filter(
        student=student, status=Grade.Status.PUBLISHED,
    ).select_related('course_offering__course')
    return _weighted_average(grades)


def get_transcript_for_student(student):
    """Every published grade for a student, grouped by semester, each
    with its own GPA, plus the overall CGPA - the full academic record.
    """
    grades = get_published_results_for_student(student).select_related(
        'course_offering__course',
    ).order_by(
        'course_offering__semester__session__name',
        'course_offering__semester__name',
        'course_offering__course__code',
    )

    semesters = {}
    for grade in grades:
        semester = grade.course_offering.semester
        semesters.setdefault(semester, []).append(grade)

    return {
        'results_by_semester': [
            {'semester': semester, 'grades': grade_list, 'gpa': compute_gpa(student, semester)}
            for semester, grade_list in semesters.items()
        ],
        'cgpa': compute_cgpa(student),
    }


def get_broadsheet_for_offering(course_offering):
    """Every HOD-approved-or-published grade for one course offering,
    the official per-course record - used for the Exam Officer's
    broadsheet, generated either just before or just after publishing.
    """
    return Grade.objects.filter(
        course_offering=course_offering,
        status__in=[Grade.Status.APPROVED, Grade.Status.PUBLISHED],
    ).select_related('student', 'student__user').order_by('student__matric_number')


def get_collated_grades(*, department=None, semester=None, status=None):
    """FR-EXM-01: every locked grade (anything past Draft - Submitted,
    Approved, Rejected, or Published) across every department, so the
    Exam Officer can see where each department stands in the review
    pipeline, not just the ones already HOD-approved.
    """
    qs = Grade.objects.exclude(status=Grade.Status.DRAFT).select_related(
        'student', 'student__user', 'course_offering', 'course_offering__course',
        'course_offering__course__department', 'course_offering__semester', 'course_offering__semester__session',
    )
    if department:
        qs = qs.filter(course_offering__course__department=department)
    if semester:
        qs = qs.filter(course_offering__semester=semester)
    if status:
        qs = qs.filter(status=status)
    return qs.order_by(
        'course_offering__course__department__code', 'course_offering__course__code', 'student__matric_number',
    )


def get_master_broadsheet(*, programme, semester, level):
    """FR-EXM-06: the pivoted academic-board broadsheet for one Programme,
    Level, and Semester - one row per student, one column per course, a
    semester GPA in the final column. Built in three independent stages,
    since conflating them is exactly how a student ends up on the wrong
    programme's sheet:

    STAGE A - COLUMNS. Which courses belong to this Programme, at this
    level/semester? Delegated entirely to
    apps.courses.selectors.get_course_offerings_for_programme - the one
    authoritative "who does this course belong to" rule, shared with
    nothing else touching student-specific eligibility (see that
    function's docstring for the exact priority order: explicit
    Programme/eligible_programmes tagging beats the department's blanket
    General Studies fallback). A course still sitting in the "No
    Programme" bucket under an ordinary department won't show up in any
    Master Broadsheet until it's tagged one way or the other.

    STAGE B - ROWS. Which students actually belong to this Programme?
    Answered ONLY by Student.programme == programme - never by course
    registration, never by course eligibility. A shared course being a
    column on two programmes' sheets does NOT make a student who took it
    appear on both; only their own Programme decides which one sheet
    they're on. Also requires Student.level == level (not merely implied
    by "registered for a level-L course" - protects against a carried-
    over/repeat-course registration putting a student on the wrong
    level's board), and excludes withdrawn/suspended students (FR-REG-05
    status semantics - a board document reflects the currently-enrolled
    cohort). A student with no Programme assigned on their own record
    won't appear on ANY Master Broadsheet - see
    apps.students.management.commands.assign_student_programme for a
    safe, dry-run-first bulk assignment tool, and
    apps.students.management.commands.inspect_student_programmes to find
    who needs one.

    STAGE C - CELLS. For each student x course in the grid above, their
    HOD-approved-or-published grade, if any - a raw, still-editable draft
    has no business appearing on a document meant for final academic
    board ratification.
    """
    from apps.courses.models import CourseOffering, CourseRegistration
    from apps.courses.selectors import get_course_offerings_for_programme
    from apps.students.models import Student

    # --- Stage A: columns ---
    offerings = list(
        get_course_offerings_for_programme(
            CourseOffering.objects.filter(course__level=level, semester=semester), programme,
        ).select_related('course').order_by('course__code')
    )
    courses = [offering.course for offering in offerings]

    # --- Stage B: rows ---
    registered_student_ids = CourseRegistration.objects.filter(
        course_offering__in=offerings, status=CourseRegistration.Status.REGISTERED,
    ).values_list('student_id', flat=True).distinct()
    students = Student.objects.filter(
        pk__in=registered_student_ids, programme=programme, level=level,
    ).exclude(
        status__in=[Student.Status.WITHDRAWN, Student.Status.SUSPENDED],
    ).select_related('user').order_by('matric_number')

    # --- Stage C: cells (only HOD-approved-or-published grades) ---
    grades_by_student_course = {}
    for grade in Grade.objects.filter(
        course_offering__in=offerings, status__in=[Grade.Status.APPROVED, Grade.Status.PUBLISHED],
    ).select_related('course_offering__course'):
        grades_by_student_course[(grade.student_id, grade.course_offering.course_id)] = grade

    rows = []
    for student in students:
        row_grades = []
        for course in courses:
            grade = grades_by_student_course.get((student.id, course.id))
            if grade:
                # Already have the student loaded - avoids grade.student
                # issuing its own query just so grade_band can resolve
                # the department/programme-scoped band (see GradeBand).
                grade.student = student
            row_grades.append(grade)

        total_points = 0.0
        total_units = 0
        has_fail = False
        for grade, course in zip(row_grades, courses):
            if grade and grade.grade_point is not None:
                total_points += float(grade.grade_point) * course.credit_units
                total_units += course.credit_units
            if grade and grade.letter_grade == 'F':
                has_fail = True
        gpa = round(total_points / total_units, 2) if total_units else None
        remark = compute_broadsheet_remark(gpa, has_fail=has_fail)
        rows.append({'student': student, 'grades': row_grades, 'gpa': gpa, 'remark': remark})

    # FR-EXM-06: Fail rows sink to the bottom of the sheet - stable sort,
    # so students sharing a remark stay in the matric-number order the
    # `students` queryset already produced.
    rows.sort(key=lambda row: REMARK_ORDER[row['remark']])

    return {'courses': courses, 'rows': rows}
