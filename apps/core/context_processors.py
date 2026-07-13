from django.conf import settings


def site_context(request):
    """Expose college identity constants to every template."""
    return {
        'COLLEGE_NAME': settings.COLLEGE_NAME,
        'COLLEGE_SHORT_NAME': settings.COLLEGE_SHORT_NAME,
    }
