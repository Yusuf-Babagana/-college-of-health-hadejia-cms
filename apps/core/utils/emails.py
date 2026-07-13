"""
Templated email sending, shared by every app that needs to notify a user
(welcome emails, payment receipts, registration confirmations, etc.).
Django's built-in password reset flow has its own email templates and
does not go through here.
"""
import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

logger = logging.getLogger('apps')


def send_templated_email(subject, template_name, context, to, from_email=None):
    """Render ``template_name`` (an HTML template) with ``context`` and send
    it as an email to ``to`` (a string or list of strings). A plain-text
    fallback is derived by stripping tags, so clients without HTML
    rendering still get something readable.
    """
    from django.utils.html import strip_tags

    recipients = [to] if isinstance(to, str) else list(to)
    html_body = render_to_string(template_name, context)
    text_body = strip_tags(html_body)

    message = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=from_email or settings.DEFAULT_FROM_EMAIL,
        to=recipients,
    )
    message.attach_alternative(html_body, 'text/html')

    try:
        message.send(fail_silently=False)
    except Exception:
        logger.exception('Failed to send email "%s" to %s', subject, recipients)
        raise

    logger.info('Sent email "%s" to %s', subject, recipients)
    return True
