"""
Business logic for fee structure, invoice, and payment management.
"""
from django.core.exceptions import ValidationError
from django.utils import timezone

from . import paystack
from .models import Invoice, Payment


def archive_fee_type(fee_type):
    fee_type.delete()  # soft delete
    return fee_type


def restore_fee_type(fee_type):
    fee_type.restore()
    return fee_type


def archive_fee_structure(fee_structure):
    fee_structure.delete()  # soft delete
    return fee_structure


def restore_fee_structure(fee_structure):
    fee_structure.restore()
    return fee_structure


def generate_invoice(*, student, fee_structure, due_date=None):
    """Individual invoice generation. Raises if this student already has
    an invoice against this exact fee structure (no accidental double
    billing) - the unique constraint would catch it too, but this gives a
    friendlier error before hitting the database.
    """
    if Invoice.objects.filter(student=student, fee_structure=fee_structure).exists():
        raise ValidationError(
            f'{student.matric_number} already has an invoice for {fee_structure}.'
        )

    return Invoice.objects.create(
        student=student,
        fee_structure=fee_structure,
        amount_due=fee_structure.amount,
        due_date=due_date,
    )


def bulk_generate_invoices(*, fee_structure, due_date=None):
    """FR-FIN-02: bulk generation for a whole department/level - every
    active student matching the fee structure's department and level who
    doesn't already have an invoice for it.
    """
    from apps.students.models import Student

    students = Student.objects.filter(
        department=fee_structure.department,
        level=fee_structure.level,
        status=Student.Status.ACTIVE,
    )
    already_billed_ids = set(
        Invoice.objects.filter(fee_structure=fee_structure).values_list('student_id', flat=True)
    )

    created = []
    for student in students:
        if student.pk in already_billed_ids:
            continue
        created.append(Invoice(
            student=student,
            fee_structure=fee_structure,
            amount_due=fee_structure.amount,
            due_date=due_date,
        ))

    Invoice.objects.bulk_create(created)
    skipped_count = students.count() - len(created)
    return len(created), skipped_count


def bulk_generate_invoices_for_all_fee_types(*, department, level, session, due_date=None):
    """Runs bulk_generate_invoices once per fee type billed to this
    department/level/session (Tuition, Registration, Practical, Board
    Exams, etc.), so the Bursar can bill every activity for a cohort in
    one action instead of repeating FR-FIN-02 fee type by fee type.
    """
    from .models import FeeStructure

    fee_structures = FeeStructure.objects.filter(
        department=department, level=level, session=session,
    ).select_related('fee_type')

    if not fee_structures.exists():
        raise ValidationError(
            'No fee structures exist yet for this department, level, and session.'
        )

    breakdown = []
    for fee_structure in fee_structures:
        created_count, skipped_count = bulk_generate_invoices(fee_structure=fee_structure, due_date=due_date)
        breakdown.append({
            'fee_type': fee_structure.fee_type.name,
            'created': created_count,
            'skipped': skipped_count,
        })

    return breakdown


def _apply_successful_payment(invoice, amount):
    """Credits a successful payment to its invoice and recomputes status -
    the one place amount_paid ever changes, so Invoice and Payment can
    never drift apart.
    """
    invoice.amount_paid = invoice.amount_paid + amount
    invoice.recompute_status()
    invoice.save(update_fields=['amount_paid', 'status', 'updated_at'])


def record_offline_payment(*, invoice, amount, reference, notes, recorded_by):
    """FR-FIN-03: Bursar manually records a bank-teller payment. Recording
    it IS the verification - there's no separate confirmation step for
    offline payments the way there is for online ones.
    """
    if Payment.objects.filter(reference=reference).exists():
        raise ValidationError('A payment with this reference already exists.')
    if amount > invoice.balance:
        raise ValidationError(
            f'Amount ({amount}) exceeds the outstanding balance ({invoice.balance}) on this invoice.'
        )

    payment = Payment.objects.create(
        invoice=invoice,
        amount=amount,
        method=Payment.Method.OFFLINE,
        reference=reference,
        status=Payment.Status.SUCCESSFUL,
        paid_at=timezone.now(),
        verified_by=recorded_by,
        notes=notes,
    )
    _apply_successful_payment(invoice, amount)
    return payment


def initiate_online_payment(*, invoice, email, callback_url, amount=None):
    """FR-FIN-03: starts a Paystack transaction for either the invoice's
    full outstanding balance or a student-chosen part payment, and
    returns the hosted checkout URL to redirect the student to. The
    Payment row records exactly what was requested, so a part payment
    still leaves the remaining balance owing once it's applied.
    """
    from apps.core.utils.generators import generate_reference_code

    if invoice.balance <= 0:
        raise ValidationError('This invoice has no outstanding balance.')

    amount = invoice.balance if amount is None else amount

    if amount <= 0:
        raise ValidationError('Payment amount must be greater than zero.')
    if amount > invoice.balance:
        raise ValidationError(
            f'Amount ({amount}) exceeds the outstanding balance ({invoice.balance}) on this invoice.'
        )

    reference = generate_reference_code(prefix='PSK-')
    amount_kobo = int(amount * 100)

    data = paystack.initialize_transaction(
        email=email,
        amount_kobo=amount_kobo,
        reference=reference,
        callback_url=callback_url,
    )

    Payment.objects.create(
        invoice=invoice,
        amount=amount,
        method=Payment.Method.ONLINE,
        reference=reference,
        status=Payment.Status.PENDING,
    )
    return data['authorization_url']


def verify_online_payment(reference):
    """Checks a pending online payment against Paystack and applies it if
    successful. Idempotent - safe to call from both the browser callback
    and the webhook for the same reference without double-crediting.
    """
    try:
        payment = Payment.objects.select_related('invoice').get(reference=reference)
    except Payment.DoesNotExist:
        raise ValidationError(f'No payment found with reference {reference}.')

    if payment.status == Payment.Status.SUCCESSFUL:
        return payment  # already applied - e.g. webhook beat the callback here

    data = paystack.verify_transaction(reference)

    if data.get('status') == 'success':
        payment.status = Payment.Status.SUCCESSFUL
        payment.paid_at = timezone.now()
        payment.save(update_fields=['status', 'paid_at', 'updated_at'])
        _apply_successful_payment(payment.invoice, payment.amount)
    else:
        payment.status = Payment.Status.FAILED
        payment.save(update_fields=['status', 'updated_at'])

    return payment
