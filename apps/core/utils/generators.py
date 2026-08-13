"""
Pure functions that generate identifiers used across the system:
matric numbers, invoice numbers, transaction references, OTPs.

These are intentionally free of DB access - callers are responsible for
checking uniqueness against their own model and retrying on collision,
since only they know which table/field to check.
"""
import random
import secrets
import string
from datetime import datetime


def generate_matric_number(department_code: str, admission_year: int, sequence: int) -> str:
    """e.g. generate_matric_number('CHE', 2025, 7) -> 'CHE/2025/0007'"""
    return f'{department_code.upper()}/{admission_year}/{sequence:04d}'


def generate_reference_code(prefix: str = '', length: int = 10) -> str:
    """Random alphanumeric reference, e.g. for payment transaction refs."""
    alphabet = string.ascii_uppercase + string.digits
    suffix = ''.join(secrets.choice(alphabet) for _ in range(length))
    return f'{prefix}{suffix}' if prefix else suffix


def generate_invoice_number(prefix: str = 'INV') -> str:
    """e.g. 'INV-20260705-4F82A1'"""
    date_part = datetime.now().strftime('%Y%m%d')
    return f'{prefix}-{date_part}-{generate_reference_code(length=6)}'


def generate_otp(length: int = 6) -> str:
    """Numeric one-time-passcode, e.g. for email/phone verification."""
    return ''.join(random.SystemRandom().choice(string.digits) for _ in range(length))


def generate_registration_slip_number(session_code: str, semester_code: str, student_sequence: int) -> str:
    return f'RS/{session_code}/{semester_code}/{student_sequence:05d}'
