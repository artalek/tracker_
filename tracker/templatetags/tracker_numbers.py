from decimal import Decimal

from django import template
from django.template.defaultfilters import floatformat
from django.utils.formats import localize

register = template.Library()


@register.filter
def rate_digits(value):
    rounded = floatformat(value, "6u").rstrip("0").rstrip(".")
    return localize(Decimal(rounded)) if rounded else ""
