"""
Business logic for fee structure, invoice, and payment management.
"""
import logging

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from . import paystack, selectors
from .models import FeeStructure, Invoice, Payment
from .models.invoice import new_invoice_number

logger = logging.getLogger('apps')


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


# --- Invoice generation -------------------------------------------------
#
# Every invoice is created by issue_invoices(). The public entry points
# below only decide WHO to bill (and for what); none of them builds or
# saves an Invoice itself, so the published check, duplicate protection,
# numbering, locking and snapshotting live in exactly one place.


def issue_invoices(*, fee_structure, students, due_date=None):
    """The single place invoices are created. Bills each of ``students``
    against ``fee_structure`` unless they already have one. Returns
    ``(created_invoices, skipped_count)``.

    Concurrency: the fee structure row is locked for the duration, so two
    simultaneous runs for the same fee (a fee save plus a manual click, or
    a student's page load) serialise, and the already-billed check below
    always sees the other run's rows - no IntegrityError, no half-created
    batch.
    """
    with transaction.atomic():
        # Authoritative copy of the fee (published flag and amount as they
        # are right now); invoices still hang off the caller's instance.
        locked = FeeStructure.objects.select_for_update().get(pk=fee_structure.pk)
        if not locked.is_published:
            raise ValidationError(f'{fee_structure} is not published, so it cannot be invoiced.')

        student_ids = [student.pk for student in students]
        already_billed = set(
            Invoice.objects.filter(fee_structure=fee_structure, student_id__in=student_ids)
            .values_list('student_id', flat=True)
        )

        invoices = [
            Invoice(
                student_id=student_id,
                fee_structure=fee_structure,
                amount_due=locked.amount,  # snapshot - later price edits never rewrite this
                due_date=due_date or locked.due_date,
                invoice_number=new_invoice_number(),
            )
            for student_id in student_ids if student_id not in already_billed
        ]
        Invoice.objects.bulk_create(invoices)

    return invoices, len(student_ids) - len(invoices)


def generate_invoice(*, student, fee_structure, due_date=None):
    """Individual (Bursar) generation. Unlike the bulk paths, billing a
    student twice for the same fee is an error to show the Bursar, not a
    silent skip.
    """
    invoices, skipped = issue_invoices(fee_structure=fee_structure, students=[student], due_date=due_date)
    if skipped:
        raise ValidationError(f'{student.matric_number} already has an invoice for {fee_structure}.')
    return invoices[0]


def bulk_generate_invoices(*, fee_structure, due_date=None):
    """FR-FIN-02: bills every student the fee structure applies to
    (selectors.get_eligible_students) who isn't already billed. Returns
    (created_count, skipped_count).
    """
    if not fee_structure.is_published:
        raise ValidationError('This fee structure is not published - publish it before generating invoices.')

    created, skipped = issue_invoices(
        fee_structure=fee_structure,
        students=selectors.get_eligible_students(fee_structure),
        due_date=due_date,
    )
    return len(created), skipped


def generate_invoices_for_published_fee(fee_structure):
    """Trigger for "a fee was created/saved": bills its eligible students
    if it is published. Returns (created, skipped), or None when the fee
    is unpublished (nothing to do). Safe to re-run - already-billed
    students are skipped and existing invoices keep their snapshot.
    """
    if not fee_structure.is_published:
        return None
    return bulk_generate_invoices(fee_structure=fee_structure)


def generate_invoices_for_level(level, programme=None):
    """Trigger for "this level's current semester changed": bills every
    eligible student of the level for the published fees of the semester
    it is now running. ``programme`` (a Programme or pk) narrows it to
    fees for that programme plus the programme-wide ones; eligibility
    still decides who is actually billed, so a programme with its own
    semester state is never billed for another programme's semester.
    Returns the total number of invoices created.
    """
    from apps.academics.selectors import get_semester_for_level

    programme_id = getattr(programme, 'pk', programme)
    semester = get_semester_for_level(level, programme_id)
    if semester is None:
        return 0

    fee_structures = FeeStructure.objects.filter(level=level, session=semester.session, is_published=True)
    if programme_id:
        fee_structures = fee_structures.filter(Q(programme_id=programme_id) | Q(programme__isnull=True))

    return sum(
        bulk_generate_invoices(fee_structure=fee_structure)[0] for fee_structure in fee_structures
    )


def sync_invoices_for_student(student):
    """Automatic visibility: makes sure a student has an invoice for every
    published fee that currently applies to them, so they never have to
    ask for one. Idempotent. Returns the newly created invoices.
    """
    if student.status != student.Status.ACTIVE:
        return []

    created = []
    for fee_structure in selectors.resolve_fee_structures_for_student(student):
        invoices, _ = issue_invoices(fee_structure=fee_structure, students=[student])
        created.extend(invoices)
    return created


def bulk_generate_invoices_for_all_fee_types(*, department, level, session, due_date=None):
    """Runs bulk_generate_invoices once per published fee structure for
    this department/level/session (Tuition, Registration, Practical,
    etc.). Eligibility already resolves most-specific-wins per student,
    so no student is billed twice for the same fee type.
    """
    fee_structures = FeeStructure.objects.filter(
        department=department, level=level, session=session, is_published=True,
    ).select_related('fee_type')

    if not fee_structures.exists():
        raise ValidationError(
            'No published fee structures exist yet for this department, level, and session.'
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
    never drift apart. Callers hold a row lock on the invoice.
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

    with transaction.atomic():
        invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
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
    """FR-FIN-03: starts a Paystack transaction for exactly THIS invoice's
    outstanding balance and returns the hosted checkout URL. The charge
    is only ever this invoice's own balance - never combined with other
    invoices, arrears or any other obligation. Part payments are not
    offered online; passing an ``amount`` that differs from the balance
    is rejected.
    """
    from apps.core.utils.generators import generate_reference_code

    if not invoice.fee_structure.is_published:
        raise ValidationError('This invoice is no longer payable.')

    # Settle any earlier checkout attempt first: if it actually went
    # through, the balance below is already reduced (no double payment);
    # if it was abandoned, it is marked failed.
    for pending in invoice.payments.filter(method=Payment.Method.ONLINE, status=Payment.Status.PENDING):
        try:
            verify_online_payment(pending.reference)
        except (ValidationError, paystack.PaystackError):
            pass
    invoice.refresh_from_db()

    if invoice.balance <= 0:
        raise ValidationError('This invoice has no outstanding balance.')
    if amount is not None and amount != invoice.balance:
        raise ValidationError(
            f'Online payment must be the invoice balance ({invoice.balance}); got {amount}.'
        )
    amount = invoice.balance

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


def _fail_payment(payment, note):
    payment.status = Payment.Status.FAILED
    payment.notes = note[:255]
    payment.save(update_fields=['status', 'notes', 'updated_at'])
    return payment


def verify_online_payment(reference):
    """Checks a pending online payment against Paystack and applies it if
    successful. Idempotent and race-safe: callback and webhook can both
    call it for the same reference without double-crediting, because the
    payment and its invoice are locked and re-checked before crediting.

    Credited only if Paystack confirms exactly the amount we asked for
    and the invoice can still take it. A confirmed charge that cannot be
    applied (wrong amount, or the invoice was settled meanwhile) is
    marked failed with a note so the Bursar can refund it - it is never
    silently over-credited.
    """
    try:
        payment = Payment.objects.get(reference=reference)
    except Payment.DoesNotExist:
        raise ValidationError(f'No payment found with reference {reference}.')

    if payment.status == Payment.Status.SUCCESSFUL:
        return payment  # already applied - e.g. webhook beat the callback here

    data = paystack.verify_transaction(reference)

    with transaction.atomic():
        payment = Payment.objects.select_for_update().get(pk=payment.pk)
        if payment.status == Payment.Status.SUCCESSFUL:
            return payment
        invoice = Invoice.objects.select_for_update().get(pk=payment.invoice_id)

        if data.get('status') != 'success':
            payment.status = Payment.Status.FAILED
            payment.save(update_fields=['status', 'updated_at'])
            return payment

        if data.get('amount') != int(payment.amount * 100):
            logger.error('Paystack amount mismatch for %s: gateway=%s expected=%s',
                         reference, data.get('amount'), int(payment.amount * 100))
            return _fail_payment(payment, 'Gateway amount did not match the amount requested - not credited; review.')
        if payment.amount > invoice.balance:
            logger.error('Paystack payment %s exceeds invoice %s balance', reference, invoice.pk)
            return _fail_payment(
                payment, 'Charged on the gateway but the invoice was already settled - not credited; refund required.',
            )

        payment.status = Payment.Status.SUCCESSFUL
        payment.paid_at = timezone.now()
        payment.save(update_fields=['status', 'paid_at', 'updated_at'])
        _apply_successful_payment(invoice, payment.amount)
        payment.invoice = invoice

    return payment
