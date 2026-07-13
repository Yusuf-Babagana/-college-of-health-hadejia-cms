from django.core.exceptions import ValidationError
from django.db import models

from apps.core.models import BaseModel


class Semester(BaseModel):
    """A semester within an academic session. There is no single globally
    "active" semester - each student level runs its own current semester,
    tracked in LevelSemesterState, since cohorts move at different paces
    (Level 100 can be in First Semester while Level 200 is in Second).
    """

    class SemesterName(models.TextChoices):
        FIRST = 'first', 'First Semester'
        SECOND = 'second', 'Second Semester'

    session = models.ForeignKey(
        'academics.AcademicSession',
        on_delete=models.PROTECT,
        related_name='semesters',
    )
    name = models.CharField(max_length=10, choices=SemesterName.choices)
    registration_start = models.DateTimeField(
        null=True, blank=True,
        help_text='When course registration opens for this semester.',
    )
    registration_end = models.DateTimeField(
        null=True, blank=True,
        help_text='When course registration closes for this semester.',
    )

    class Meta:
        verbose_name = 'Semester'
        verbose_name_plural = 'Semesters'
        ordering = ['-session__name', 'name']
        constraints = [
            models.UniqueConstraint(fields=['session', 'name'], name='unique_semester_per_session'),
        ]

    def __str__(self):
        return f'{self.get_name_display()} - {self.session.name}'

    def clean(self):
        if self.registration_start and self.registration_end and self.registration_end <= self.registration_start:
            raise ValidationError({'registration_end': 'Registration close date must be after the open date.'})

    @property
    def is_registration_open(self):
        if not (self.registration_start and self.registration_end):
            return False
        from django.utils import timezone
        now = timezone.now()
        return self.registration_start <= now <= self.registration_end
