from django import template

from apps.core.utils.formatters import format_naira

register = template.Library()

register.filter('naira', format_naira)
