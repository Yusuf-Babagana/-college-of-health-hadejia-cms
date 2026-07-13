"""
Read-only queries for fee structures and invoices.
"""
from .models import FeeStructure, FeeType, Invoice


def get_fee_type_list(*, include_archived=False):
    manager = FeeType.all_objects if include_archived else FeeType.objects
    return manager.all()


def get_active_fee_types():
    return FeeType.objects.all()


def get_fee_structure_list(*, session=None, department=None, level=None, fee_type=None, include_archived=False):
    manager = FeeStructure.all_objects if include_archived else FeeStructure.objects
    qs = manager.select_related('department', 'session', 'fee_type')

    if session:
        qs = qs.filter(session_id=session)
    if department:
        qs = qs.filter(department_id=department)
    if level:
        qs = qs.filter(level=level)
    if fee_type:
        qs = qs.filter(fee_type_id=fee_type)

    return qs


def get_fee_structure_for(*, department, level, session, fee_type):
    """Used by invoice generation to look up what a given student owes
    for a specific fee type (Tuition, Practical, Board Exam, etc.)."""
    return FeeStructure.objects.filter(
        department=department, level=level, session=session, fee_type=fee_type,
    ).first()


def get_invoice_list(*, session=None, department=None, level=None, status=None, fee_type=None, include_archived=False):
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

    return qs


def get_invoices_for_student(student):
    return Invoice.objects.filter(student=student).select_related('fee_structure', 'fee_structure__session')


def get_outstanding_balance_for_student(student):
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
