"""Business logic for the admissions payment flow. Mirrors
apps.finance.services.initiate_online_payment / verify_online_payment, but
against a fixed application fee instead of a variable invoice balance.
"""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.finance import paystack

from .models import AdmissionPayment


def initiate_admission_payment(*, applicant, email, callback_url):
    """Starts a Paystack transaction for the fixed admission application fee
    and returns the hosted checkout URL to redirect the applicant to.
    """
    from apps.core.utils.generators import generate_reference_code

    reference = generate_reference_code(prefix='ADM-')
    amount = settings.ADMISSIONS_APPLICATION_FEE
    amount_kobo = int(amount * 100)

    data = paystack.initialize_transaction(
        email=email,
        amount_kobo=amount_kobo,
        reference=reference,
        callback_url=callback_url,
    )

    AdmissionPayment.objects.create(
        applicant=applicant,
        amount=amount,
        reference=reference,
        status=AdmissionPayment.Status.PENDING,
    )
    return data['authorization_url']


def verify_admission_payment(reference):
    """Checks a pending admission payment against Paystack and applies it if
    successful. Idempotent - safe to call from both the browser callback and
    the webhook for the same reference without double-crediting.
    """
    try:
        payment = AdmissionPayment.objects.select_related('applicant').get(reference=reference)
    except AdmissionPayment.DoesNotExist:
        raise ValidationError(f'No admission payment found with reference {reference}.')

    if payment.status == AdmissionPayment.Status.SUCCESSFUL:
        return payment  # already applied - e.g. webhook beat the callback here

    data = paystack.verify_transaction(reference)
    payment.raw_response = data

    if data.get('status') == 'success':
        payment.status = AdmissionPayment.Status.SUCCESSFUL
        payment.paid_at = timezone.now()
        payment.save(update_fields=['status', 'paid_at', 'raw_response', 'updated_at'])

        applicant = payment.applicant
        applicant.has_paid = True
        applicant.payment_verified_at = timezone.now()
        applicant.save(update_fields=['has_paid', 'payment_verified_at', 'updated_at'])
    else:
        payment.status = AdmissionPayment.Status.FAILED
        payment.save(update_fields=['status', 'raw_response', 'updated_at'])

    return payment
