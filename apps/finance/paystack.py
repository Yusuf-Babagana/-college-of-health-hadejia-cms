"""
Thin client for the Paystack Transactions API.
https://paystack.com/docs/api/transaction/
https://paystack.com/docs/payments/webhooks/
"""
import hashlib
import hmac
import logging

import requests
from django.conf import settings

logger = logging.getLogger('apps')

BASE_URL = 'https://api.paystack.co'
TIMEOUT = 15


class PaystackError(Exception):
    """Raised when Paystack rejects a request or is unreachable."""


def _headers():
    return {
        'Authorization': f'Bearer {settings.PAYSTACK_SECRET_KEY}',
        'Content-Type': 'application/json',
    }


def initialize_transaction(*, email, amount_kobo, reference, callback_url):
    """Starts a transaction and returns Paystack's response data, which
    includes 'authorization_url' - the hosted checkout page to redirect
    the payer to.
    """
    try:
        response = requests.post(
            f'{BASE_URL}/transaction/initialize',
            json={
                'email': email,
                'amount': amount_kobo,
                'reference': reference,
                'callback_url': callback_url,
            },
            headers=_headers(),
            timeout=TIMEOUT,
        )
    except requests.RequestException as exc:
        logger.exception('Paystack initialize_transaction request failed')
        raise PaystackError('Could not reach Paystack. Try again shortly.') from exc

    data = response.json()
    if not data.get('status'):
        raise PaystackError(data.get('message', 'Failed to initialize transaction.'))
    return data['data']


def verify_transaction(reference):
    """Checks a transaction's real status directly with Paystack - the
    source of truth, used by both the callback view and the webhook."""
    try:
        response = requests.get(
            f'{BASE_URL}/transaction/verify/{reference}',
            headers=_headers(),
            timeout=TIMEOUT,
        )
    except requests.RequestException as exc:
        logger.exception('Paystack verify_transaction request failed')
        raise PaystackError('Could not reach Paystack. Try again shortly.') from exc

    data = response.json()
    if not data.get('status'):
        raise PaystackError(data.get('message', 'Failed to verify transaction.'))
    return data['data']


def verify_webhook_signature(request):
    """Confirms a webhook request genuinely came from Paystack, per their
    documented HMAC-SHA512 scheme, before trusting its payload.
    """
    signature = request.headers.get('x-paystack-signature', '')
    computed = hmac.new(
        settings.PAYSTACK_SECRET_KEY.encode('utf-8'),
        request.body,
        hashlib.sha512,
    ).hexdigest()
    return hmac.compare_digest(computed, signature)
