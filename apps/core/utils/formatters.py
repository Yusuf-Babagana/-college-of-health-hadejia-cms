"""
Presentation-layer formatting helpers for templates and PDFs: currency,
GPA, file sizes, human names.
"""
from decimal import Decimal


def format_naira(amount) -> str:
    """1234.5 -> '₦1,234.50'"""
    value = Decimal(amount or 0)
    return f'₦{value:,.2f}'


_ONES = (
    'Zero', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine', 'Ten', 'Eleven',
    'Twelve', 'Thirteen', 'Fourteen', 'Fifteen', 'Sixteen', 'Seventeen', 'Eighteen', 'Nineteen',
)
_TENS = ('', '', 'Twenty', 'Thirty', 'Forty', 'Fifty', 'Sixty', 'Seventy', 'Eighty', 'Ninety')
_SCALES = ((10 ** 9, 'Billion'), (10 ** 6, 'Million'), (10 ** 3, 'Thousand'))


def _words_below_thousand(number: int) -> str:
    parts = []
    if number >= 100:
        parts.append(f'{_ONES[number // 100]} Hundred')
        number %= 100
        if number:
            parts.append('and')
    if number >= 20:
        parts.append(_TENS[number // 10] + (f'-{_ONES[number % 10]}' if number % 10 else ''))
    elif number or not parts:
        parts.append(_ONES[number])
    return ' '.join(parts)


def _integer_in_words(number: int) -> str:
    if number == 0:
        return 'Zero'
    parts = []
    for scale, label in _SCALES:
        if number >= scale:
            parts.append(f'{_words_below_thousand(number // scale)} {label}')
            number %= scale
    if number:
        # "One Thousand and Fifty" reads better than "One Thousand Fifty"
        tail = _words_below_thousand(number)
        parts.append(f'and {tail}' if parts and number < 100 else tail)
    return ' '.join(parts)


def amount_in_words(amount) -> str:
    """Decimal('52500.50') -> 'Fifty-Two Thousand Five Hundred Naira, Fifty Kobo Only'."""
    value = Decimal(amount or 0).quantize(Decimal('0.01'))
    naira, kobo = int(value), int((value - int(value)) * 100)
    parts = []
    if naira or not kobo:
        parts.append(f'{_integer_in_words(naira)} Naira')
    if kobo:
        parts.append(f'{_integer_in_words(kobo)} Kobo')
    return ', '.join(parts) + ' Only'


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
