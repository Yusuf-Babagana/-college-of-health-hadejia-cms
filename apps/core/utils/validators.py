"""
Reusable Django validators shared across apps, so field-level validation
rules (phone numbers, file sizes, allowed extensions) are defined once.
"""
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator

phone_number_validator = RegexValidator(
    regex=r'^\+?[0-9]{10,14}$',
    message='Enter a valid phone number.',
)

matric_number_validator = RegexValidator(
    regex=r'^[A-Z]{2,6}/\d{2,4}/\d{3,6}$',
    message='Enter a valid matric number, e.g. CHE/2025/0001.',
)

academic_session_name_validator = RegexValidator(
    regex=r'^\d{4}/\d{4}$',
    message='Enter a session in the format YYYY/YYYY, e.g. 2025/2026.',
)


def validate_file_size(file, max_mb=5):
    max_bytes = max_mb * 1024 * 1024
    if file.size > max_bytes:
        raise ValidationError(f'File must not exceed {max_mb}MB.')


def validate_image_file(file):
    valid_extensions = ('.jpg', '.jpeg', '.png', '.webp')
    if not str(file.name).lower().endswith(valid_extensions):
        raise ValidationError(
            f'Unsupported file type. Allowed: {", ".join(valid_extensions)}'
        )
    validate_file_size(file, max_mb=2)


def validate_pdf_file(file):
    if not str(file.name).lower().endswith('.pdf'):
        raise ValidationError('Only PDF files are allowed.')
    validate_file_size(file, max_mb=10)


def validate_document_file(file):
    """Accepts either a scanned image or a PDF - for supporting documents
    (certificates, result slips) where either format is normal to receive.
    """
    valid_extensions = ('.jpg', '.jpeg', '.png', '.webp', '.pdf')
    if not str(file.name).lower().endswith(valid_extensions):
        raise ValidationError(
            f'Unsupported file type. Allowed: {", ".join(valid_extensions)}'
        )
    validate_file_size(file, max_mb=10)


def validate_positive_amount(value):
    if value <= 0:
        raise ValidationError('Amount must be greater than zero.')
