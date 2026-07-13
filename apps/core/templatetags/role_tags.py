from django import template

register = template.Library()


@register.filter
def has_role(user, role_name):
    """Usage in templates: {% if request.user|has_role:"student" %}"""
    return getattr(user, 'role', None) == role_name
