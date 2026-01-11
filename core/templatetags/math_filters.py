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


@register.filter
def indian_number_format(value):
    """
    Format number with Indian number system commas (1,00,000 style).
    Returns formatted number WITHOUT currency symbol.
    Example: 1000000 -> "10,00,000"
    Use this for input fields or when you want number without ₹ symbol.
    
    CRITICAL: Always converts to integer before formatting to avoid decimal issues.
    """
    if value is None:
        return ""
    
    try:
        # CRITICAL: Handle Decimal objects from database
        if isinstance(value, Decimal):
            value = float(value)
        
        # CRITICAL: Force integer conversion FIRST (handles floats, strings, etc.)
        # This prevents issues like "10.0" being formatted as "10,0.0"
        # Use round() then int() to properly handle floats
        num = int(round(float(value)))
        
        # Handle zero
        if num == 0:
            return "0"
        
        # Handle negative numbers
        is_negative = num < 0
        num_abs = abs(num)
        
        # Convert to string (already integer, guaranteed no decimals)
        # Use format to ensure no decimal point
        num_str = f"{num_abs:.0f}" if isinstance(num_abs, float) else str(int(num_abs))
        
        # Get last 3 digits
        last_three = num_str[-3:]
        # Get remaining digits
        other_digits = num_str[:-3]
        
        # Add commas every 2 digits for remaining numbers (Indian format)
        if other_digits:
            # Reverse, add commas every 2 digits, reverse back
            reversed_other = other_digits[::-1]
            formatted_other = ','.join(
                reversed_other[i:i+2] for i in range(0, len(reversed_other), 2)
            )[::-1]
            result = formatted_other + ',' + last_three
        else:
            result = last_three
        
        # Add negative sign if original was negative
        if is_negative:
            result = '-' + result
        
        return result
    except (ValueError, TypeError):
        return str(value)


@register.filter
def currency_inr(value):
    """
    Format number as Indian Rupee currency with ₹ symbol and commas.
    Use this for ALL display values (tables, cards, labels, reports, etc.).
    Example: 1000000 -> "₹10,00,000"
    
    CRITICAL: Always converts to integer before formatting to avoid decimal issues.
    This prevents "10.0" from being formatted as "₹10,0.0"
    """
    if value is None:
        return "₹0"
    
    try:
        # CRITICAL: Handle Decimal objects from database
        if isinstance(value, Decimal):
            value = float(value)
        
        # CRITICAL: Force integer conversion FIRST (handles floats, strings, etc.)
        # This prevents issues like "10.0" being formatted as "₹10,0.0"
        # Use round() then int() to properly handle floats
        num = int(round(float(value)))
        
        # Handle zero
        if num == 0:
            return "₹0"
        
        # Handle negative numbers
        is_negative = num < 0
        num_abs = abs(num)
        
        # CRITICAL: Convert to string AFTER integer conversion (guaranteed no decimals)
        # This ensures we never format a float string like "10.0"
        # Use format to ensure no decimal point
        num_str = f"{num_abs:.0f}" if isinstance(num_abs, float) else str(int(num_abs))
        
        # Get last 3 digits
        last_three = num_str[-3:]
        # Get remaining digits
        other_digits = num_str[:-3]
        
        # Add commas every 2 digits for remaining numbers (Indian format)
        if other_digits:
            # Reverse, add commas every 2 digits, reverse back
            reversed_other = other_digits[::-1]
            formatted_other = ','.join(
                reversed_other[i:i+2] for i in range(0, len(reversed_other), 2)
            )[::-1]
            formatted = formatted_other + ',' + last_three
        else:
            formatted = last_three
        
        # Add currency symbol and negative sign
        return ("-₹" if is_negative else "₹") + formatted
    except (ValueError, TypeError):
        return "₹0"
