"""
General-purpose helpers that don't belong to a specific domain app.
"""
from django.utils.text import slugify


def get_client_ip(request):
    """Best-effort client IP lookup, aware of a reverse proxy in front of
    the app (e.g. Nginx setting X-Forwarded-For).
    """
    forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded_for:
        return forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def is_htmx_request(request):
    return request.headers.get('HX-Request') == 'true'


def build_absolute_url(request, path):
    """Turn a relative path into an absolute URL using the current request's
    scheme and host. Useful in emails/PDFs generated outside a template
    context that already has ``request``.
    """
    return request.build_absolute_uri(path)


def unique_slug(instance, value, slug_field_name='slug'):
    """Generate a slug for ``value`` that is unique for ``instance``'s model,
    appending -2, -3, ... on collision. Excludes the instance itself so
    saving an existing record doesn't churn its own slug.
    """
    base_slug = slugify(value)
    model_class = instance.__class__
    slug = base_slug
    counter = 2
    queryset = model_class._default_manager.all()
    if instance.pk:
        queryset = queryset.exclude(pk=instance.pk)
    while queryset.filter(**{slug_field_name: slug}).exists():
        slug = f'{base_slug}-{counter}'
        counter += 1
    return slug


def chunked(iterable, size):
    """Yield successive chunks of ``size`` from a sequence."""
    for i in range(0, len(iterable), size):
        yield iterable[i:i + size]
