"""
Read-only queries for the Practical Coordinator's placement sheet.
"""
from .models import PracticalPlacement


def get_practical_fee_types():
    """Fee types that look like the Practical fee, for the coordinator's
    fee-type picker - matched by name rather than hardcoded, since the
    Bursar names/renames fee types freely.
    """
    from apps.finance.models import FeeType

    return FeeType.objects.filter(name__icontains='practical')


def get_paid_invoices_for_fee_type(*, fee_type, session=None, fully_paid_only=False):
    """Invoices under the given fee type that have at least one payment
    applied - the source list of "who paid for practical fee".
    """
    from apps.finance.models import Invoice

    qs = Invoice.objects.filter(fee_structure__fee_type=fee_type)
    qs = qs.filter(status=Invoice.Status.PAID) if fully_paid_only else qs.exclude(status=Invoice.Status.PENDING)
    if session:
        qs = qs.filter(fee_structure__session_id=session)

    return qs.select_related(
        'student', 'student__user', 'student__department',
        'fee_structure', 'fee_structure__session',
    )


def get_placement_list(*, fee_type=None, session=None):
    qs = PracticalPlacement.objects.select_related(
        'student', 'student__user', 'student__department',
        'invoice', 'invoice__fee_structure', 'invoice__fee_structure__fee_type',
        'invoice__fee_structure__session',
    )
    if fee_type:
        qs = qs.filter(invoice__fee_structure__fee_type_id=fee_type)
    if session:
        qs = qs.filter(invoice__fee_structure__session_id=session)
    return qs
