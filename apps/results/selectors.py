"""
Read-only queries for grade bands, grade entry queues, review queues,
and published results/GPA.
"""
from .models import Grade, GradeBand


def get_grade_bands():
    return GradeBand.objects.all()


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
    """FR-EXM-06: the pivoted academic-board broadsheet - one row per
    student, one column per course offered to that programme+level in
    that semester, with a semester GPA in the final column.

    Scoped by Programme rather than Department: a department like
    Community Health can run several programmes (e.g. CHEW, JCHEW) whose
    curricula differ, so "every course in the department at this level"
    would mix courses that don't actually belong together on one board
    document. A course counts as this programme's either by having it as
    its primary Programme, or by cross-listing it via eligible_programmes
    (same rule apps.courses.selectors.is_offering_eligible_for_student
    uses for registration) - e.g. a shared GST course taken by several
    programmes appears on every one of their broadsheets, not just
    whichever programme happens to be set as its single "owner". A
    course still sitting in the "No Programme" bucket (primary Programme
    blank, and not cross-listed to this one either) won't show up in any
    Master Broadsheet until it's tagged one way or the other.
    """
    from django.db.models import Q

    from apps.courses.models import CourseOffering, CourseRegistration
    from apps.students.models import Student

    offerings = list(
        CourseOffering.objects.filter(
            Q(course__programme=programme) | Q(course__eligible_programmes=programme),
            course__level=level, semester=semester,
        ).select_related('course').order_by('course__code').distinct()
    )
    courses = [offering.course for offering in offerings]

    student_ids = CourseRegistration.objects.filter(
        course_offering__in=offerings, status=CourseRegistration.Status.REGISTERED,
    ).values_list('student_id', flat=True).distinct()
    students = Student.objects.filter(pk__in=student_ids).select_related('user').order_by('matric_number')

    # Only HOD-approved-or-published grades belong on a document meant
    # for final academic board ratification - a raw, still-editable
    # draft has no business appearing here.
    grades_by_student_course = {}
    for grade in Grade.objects.filter(
        course_offering__in=offerings, status__in=[Grade.Status.APPROVED, Grade.Status.PUBLISHED],
    ).select_related('course_offering__course'):
        grades_by_student_course[(grade.student_id, grade.course_offering.course_id)] = grade

    rows = []
    for student in students:
        row_grades = [grades_by_student_course.get((student.id, course.id)) for course in courses]
        total_points = 0.0
        total_units = 0
        for grade, course in zip(row_grades, courses):
            if grade and grade.grade_point is not None:
                total_points += float(grade.grade_point) * course.credit_units
                total_units += course.credit_units
        gpa = round(total_points / total_units, 2) if total_units else None
        rows.append({'student': student, 'grades': row_grades, 'gpa': gpa})

    return {'courses': courses, 'rows': rows}
