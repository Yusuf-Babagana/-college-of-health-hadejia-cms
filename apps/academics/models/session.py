from django.core.exceptions import ValidationError
from django.db import models

from apps.core.models import BaseModel
from apps.core.utils.validators import academic_session_name_validator


class AcademicSession(BaseModel):
    """A single academic year, e.g. 2025/2026."""

    name = models.CharField(
        max_length=9, unique=True,
        validators=[academic_session_name_validator],
        help_text='Format: YYYY/YYYY, e.g. 2025/2026.',
    )
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name = 'Academic Session'
        verbose_name_plural = 'Academic Sessions'
        ordering = ['-name']

    def __str__(self):
        return self.name

    def clean(self):
        if self.name and '/' in self.name:
            first, _, second = self.name.partition('/')
            if first.isdigit() and second.isdigit() and int(second) != int(first) + 1:
                raise ValidationError({'name': 'The second year must be exactly one year after the first, e.g. 2025/2026.'})

        if self.start_date and self.end_date and self.end_date <= self.start_date:
            raise ValidationError({'end_date': 'End date must be after the start date.'})
