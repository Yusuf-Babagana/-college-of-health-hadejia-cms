"""
Read-only queries for fee structures and invoices.
"""
from django.db import models

from .models import FeeStructure, FeeType, Invoice


def get_fee_type_list(*, include_archived=False):
    manager = FeeType.all_objects if include_archived else FeeType.objects
    return manager.all()


def get_active_fee_types():
    return FeeType.objects.all()


def get_fee_structure_list(*, session=None, department=None, level=None, fee_type=None, programme=None, include_archived=False):
    manager = FeeStructure.all_objects if include_archived else FeeStructure.objects
    qs = manager.select_related('department', 'programme', 'session', 'semester', 'fee_type')

    if session:
        qs = qs.filter(session_id=session)
    if department:
        qs = qs.filter(department_id=department)
    if level:
        qs = qs.filter(level=level)
    if fee_type:
        qs = qs.filter(fee_type_id=fee_type)
    if programme:
        qs = qs.filter(programme_id=programme)

    return qs


def get_fee_structure_for(*, department, level, session, fee_type, programme=None, semester=None):
    """Used by invoice generation to look up what a given student owes
    for a specific fee type (Tuition, Practical, Board Exam, etc.).

    Most-specific-wins, same resolution style as results.GradeBand: a
    fee scoped to this exact Programme+Semester beats one scoped to just
    the Programme, which beats one scoped to just the Semester, which
    beats the department/session-wide default (both blank). Programme/
    Semester are independent optional axes - Programme is checked first
    on ties since it tends to be the more consequential differentiator.
    """
    base = FeeStructure.objects.filter(
        department=department, level=level, session=session, fee_type=fee_type, is_published=True,
    )

    if programme and semester:
        match = base.filter(programme=programme, semester=semester).first()
        if match:
            return match
    if programme:
        match = base.filter(programme=programme, semester__isnull=True).first()
        if match:
            return match
    if semester:
        match = base.filter(programme__isnull=True, semester=semester).first()
        if match:
            return match
    return base.filter(programme__isnull=True, semester__isnull=True).first()


def resolve_fee_structure_for_scope(*, department, level, programme_id, fee_type):
    """The one published FeeStructure that bills a student in this
    department/level/programme for a fee type right now - or None. The
    semester and session come from the level's current semester (see
    academics.selectors.get_semester_for_level), so a fee for another
    session or semester never matches. Most-specific-wins applies, so a
    student is only ever billed one fee structure per fee type.
    """
    from apps.academics.selectors import get_semester_for_level

    semester = get_semester_for_level(level, programme_id)
    if semester is None:
        return None
    return get_fee_structure_for(
        department=department, level=level, session=semester.session,
        fee_type=fee_type, programme=programme_id, semester=semester,
    )


def get_eligible_students(fee_structure):
    """Active students this fee structure actually bills: right
    department, level and programme (a fee with no programme covers the
    whole department), whose level is currently running the fee's
    session/semester, and for whom this fee is the most specific match.
    Single source of truth for generation, the eligible-students screen
    and the student invoice list.
    """
    from django.db.models import Q

    from apps.students.models import Student

    if not fee_structure.is_published:
        return Student.objects.none()

    candidates = Student.objects.filter(
        department=fee_structure.department_id, level=fee_structure.level, status=Student.Status.ACTIVE,
    )
    if fee_structure.programme_id:
        candidates = candidates.filter(programme=fee_structure.programme_id)

    matching_programmes = [
        programme_id
        for programme_id in candidates.values_list('programme_id', flat=True).distinct()
        if resolve_fee_structure_for_scope(
            department=fee_structure.department_id, level=fee_structure.level,
            programme_id=programme_id, fee_type=fee_structure.fee_type_id,
        ) == fee_structure
    ]
    if not matching_programmes:
        return Student.objects.none()

    query = Q(programme_id__in=[pk for pk in matching_programmes if pk is not None])
    if None in matching_programmes:
        query |= Q(programme__isnull=True)
    return candidates.filter(query)


def get_invoice_list(*, session=None, department=None, level=None, status=None, fee_type=None,
                     programme=None, search=None, include_archived=False):
    manager = Invoice.all_objects if include_archived else Invoice.objects
    qs = manager.select_related(
        'student', 'student__user', 'fee_structure',
        'fee_structure__department', 'fee_structure__session', 'fee_structure__fee_type',
    )

    if session:
        qs = qs.filter(fee_structure__session_id=session)
    if department:
        qs = qs.filter(fee_structure__department_id=department)
    if level:
        qs = qs.filter(fee_structure__level=level)
    if fee_type:
        qs = qs.filter(fee_structure__fee_type_id=fee_type)
    if status:
        qs = qs.filter(status=status)
    if programme:
        qs = qs.filter(fee_structure__programme_id=programme)
    if search:
        qs = qs.filter(
            models.Q(invoice_number__icontains=search) | models.Q(student__matric_number__icontains=search)
        )

    return qs


def get_invoices_for_student(student):
    """A student's own invoices. Backend-enforced: only rows owned by
    this student, and never one whose fee has been deactivated
    (unpublished) unless money has already been paid against it - that
    history stays visible.
    """
    return Invoice.objects.filter(student=student).filter(
        models.Q(fee_structure__is_published=True) | models.Q(amount_paid__gt=0),
    ).select_related('fee_structure', 'fee_structure__session', 'fee_structure__fee_type')


def get_programme_invoice_report(*, session=None):
    """Invoice generation and payment performance per programme (fees
    with no programme are grouped as 'All programmes')."""
    from django.db.models import Count, Q, Sum

    qs = Invoice.objects.all()
    if session:
        qs = qs.filter(fee_structure__session_id=session)

    rows = qs.values(
        'fee_structure__programme_id', 'fee_structure__programme__name',
    ).annotate(
        invoice_count=Count('id'),
        expected=Sum('amount_due'),
        collected=Sum('amount_paid'),
        paid=Count('id', filter=Q(status=Invoice.Status.PAID)),
        partial=Count('id', filter=Q(status=Invoice.Status.PARTIALLY_PAID)),
        pending=Count('id', filter=Q(status=Invoice.Status.PENDING)),
    ).order_by('fee_structure__programme__name')

    report = []
    for row in rows:
        expected = row['expected'] or 0
        collected = row['collected'] or 0
        report.append({
            'programme_id': row['fee_structure__programme_id'],
            'programme_name': row['fee_structure__programme__name'] or 'All programmes',
            'invoice_count': row['invoice_count'],
            'expected': expected,
            'collected': collected,
            'outstanding': expected - collected,
            'paid': row['paid'],
            'partial': row['partial'],
            'pending': row['pending'],
            'percent_collected': round(collected / expected * 100, 1) if expected else 0,
        })
    return report


def get_outstanding_balance_for_student(student):
    """Display-only total of what a student still owes across invoices.
    Never used to compute an amount payable - every payment is charged
    against exactly one invoice's own balance."""
    from django.db.models import F, Sum

    result = get_invoices_for_student(student).exclude(status=Invoice.Status.PAID).aggregate(
        total=Sum(F('amount_due') - F('amount_paid')),
    )
    return result['total'] or 0


def is_student_cleared(student, session):
    """FR-FIN-04: a student is financially cleared for a session if they
    have no unpaid/partially-paid invoice against it. No invoice at all
    for that session counts as cleared too - a student can't be blocked
    for a bill Finance never issued.
    """
    return not Invoice.objects.filter(
        student=student, fee_structure__session=session,
    ).exclude(status=Invoice.Status.PAID).exists()


def get_defaulters(*, session=None, sessions=None, department=None):
    """FR-FIN-05: students with an outstanding balance past their
    invoice's due date. Scope with either one session or an iterable of
    sessions (e.g. every session currently in progress for some level).
    """
    from django.utils import timezone

    qs = Invoice.objects.exclude(status=Invoice.Status.PAID).filter(
        due_date__isnull=False, due_date__lt=timezone.now().date(),
    ).select_related('student', 'student__user', 'fee_structure', 'fee_structure__department', 'fee_structure__session')

    if session:
        qs = qs.filter(fee_structure__session_id=session)
    if sessions is not None:
        qs = qs.filter(fee_structure__session__in=sessions)
    if department:
        qs = qs.filter(fee_structure__department_id=department)

    return qs


def get_financial_summary(*, session=None, sessions=None):
    """FR-FIN-06: aggregate revenue figures, optionally scoped to one
    session or an iterable of sessions.
    """
    from django.db.models import Sum

    qs = Invoice.objects.all()
    if session:
        qs = qs.filter(fee_structure__session=session)
    if sessions is not None:
        qs = qs.filter(fee_structure__session__in=sessions)

    totals = qs.aggregate(expected=Sum('amount_due'), collected=Sum('amount_paid'))
    expected = totals['expected'] or 0
    collected = totals['collected'] or 0
    return {
        'expected': expected,
        'collected': collected,
        'outstanding': expected - collected,
        'invoice_count': qs.count(),
    }


def get_financial_summary_by_fee_type(*, session=None, sessions=None):
    """Same figures as get_financial_summary, broken down per fee type -
    lets the Bursar see e.g. Tuition is 90% collected while Practical Fee
    is only 40%, instead of one lump revenue number across every activity.
    """
    from django.db.models import Count, Sum

    qs = Invoice.objects.all()
    if session:
        qs = qs.filter(fee_structure__session=session)
    if sessions is not None:
        qs = qs.filter(fee_structure__session__in=sessions)

    rows = qs.values(
        'fee_structure__fee_type__id', 'fee_structure__fee_type__name',
    ).annotate(
        expected=Sum('amount_due'),
        collected=Sum('amount_paid'),
        invoice_count=Count('id'),
    ).order_by('fee_structure__fee_type__name')

    summary = []
    for row in rows:
        expected = row['expected'] or 0
        collected = row['collected'] or 0
        summary.append({
            'fee_type_id': row['fee_structure__fee_type__id'],
            'fee_type_name': row['fee_structure__fee_type__name'],
            'expected': expected,
            'collected': collected,
            'outstanding': expected - collected,
            'invoice_count': row['invoice_count'],
            'percent_collected': round(collected / expected * 100, 1) if expected else 0,
        })
    return summary
