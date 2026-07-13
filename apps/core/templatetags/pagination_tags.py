from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def querystring_replace(context, **kwargs):
    """Return the current request's querystring with the given params
    replaced (or removed, if the value is None), so pagination links can
    change ``page`` without dropping active search/filter params.

    Usage: <a href="{% querystring_replace page=3 %}">3</a>
    """
    request = context['request']
    params = request.GET.copy()
    for key, value in kwargs.items():
        if value is None:
            params.pop(key, None)
        else:
            params[key] = value
    query = params.urlencode()
    return f'?{query}' if query else ''


@register.simple_tag
def elided_page_range(paginator, number, on_each_side=1, on_ends=1):
    """Wraps Paginator.get_elided_page_range - Django templates can't call
    a method with keyword arguments directly, so this exposes it as a tag.
    Usage: {% elided_page_range page_obj.paginator page_obj.number as pages %}
    """
    return paginator.get_elided_page_range(number, on_each_side=on_each_side, on_ends=on_ends)
