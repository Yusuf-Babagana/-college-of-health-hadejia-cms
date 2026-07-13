"""
Business logic for the Practical Coordinator's placement sheet.
"""
from . import selectors
from .models import PracticalPlacement


def sync_placements_for_fee_type(*, fee_type, session=None):
    """Ensures every invoice that has paid (in full or in part) against
    this fee type has a PracticalPlacement row to edit - so the moment a
    student clears their Practical fee, the Coordinator sees them on the
    sheet with no manual "add row" step. Safe to call on every page load:
    get_or_create is a no-op for invoices already synced.
    """
    invoices = selectors.get_paid_invoices_for_fee_type(fee_type=fee_type, session=session)
    existing_invoice_ids = set(
        PracticalPlacement.objects.filter(invoice__in=invoices).values_list('invoice_id', flat=True)
    )

    new_placements = [
        PracticalPlacement(invoice=invoice, student=invoice.student)
        for invoice in invoices
        if invoice.pk not in existing_invoice_ids
    ]
    if new_placements:
        PracticalPlacement.objects.bulk_create(new_placements)
