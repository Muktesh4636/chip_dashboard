from django import template
from decimal import Decimal
import builtins

register = template.Library()


@register.filter
def abs(value):
    """
    Return the absolute value of a number.
    Works with Decimal, int, float, and None values.
    """
    if value is None:
        return None
    try:
        if isinstance(value, Decimal):
            return builtins.abs(value)
        return builtins.abs(float(value))
    except (TypeError, ValueError):
        return value
