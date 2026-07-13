"""
Presentation-layer formatting helpers for templates and PDFs: currency,
GPA, file sizes, human names.
"""
from decimal import Decimal


def format_naira(amount) -> str:
    """1234.5 -> '₦1,234.50'"""
    value = Decimal(amount or 0)
    return f'₦{value:,.2f}'


def format_gpa(value, decimal_places: int = 2) -> str:
    if value is None:
        return '—'
    return f'{Decimal(value):.{decimal_places}f}'


def format_file_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ('B', 'KB', 'MB', 'GB'):
        if size < 1024 or unit == 'GB':
            return f'{size:.1f} {unit}' if unit != 'B' else f'{int(size)} {unit}'
        size /= 1024
    return f'{size:.1f} GB'


def format_full_name(first_name: str, last_name: str, middle_name: str = '') -> str:
    parts = [first_name, middle_name, last_name]
    return ' '.join(p for p in parts if p).strip()


def mask_email(email: str) -> str:
    """'jane.doe@example.com' -> 'ja***@example.com'"""
    try:
        local, domain = email.split('@', 1)
    except ValueError:
        return email
    visible = local[:2]
    return f'{visible}***@{domain}'
