from django.db import models

from apps.core.models import BaseModel


class Department(BaseModel):
    """A department within the college, e.g. Community Health Extension."""

    name = models.CharField(max_length=150, unique=True)
    code = models.CharField(
        max_length=20, unique=True,
        help_text='Short code used in course prefixes, e.g. CHE, EHS.',
    )
    description = models.TextField(blank=True)
    is_general_studies = models.BooleanField(
        default=False,
        help_text='General Studies (or similar): courses under this department are '
                   'available to every student at the matching level, not just its own '
                   'students. Its HOD still assigns/allocates its courses like any other HOD.',
    )
    hod = models.ForeignKey(
        'lecturers.Lecturer',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='headed_department',
        verbose_name='Head of Department',
        help_text='Must be a lecturer already assigned to this department.',
    )

    class Meta:
        verbose_name = 'Department'
        verbose_name_plural = 'Departments'
        ordering = ['name']

    def __str__(self):
        return f'{self.name} ({self.code})'

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.code:
            self.code = self.code.strip().upper()
        if self.hod_id and self.hod.department_id and self.hod.department_id != self.pk:
            raise ValidationError({'hod': 'The Head of Department must belong to this department.'})
