from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core.constants import Level
from apps.core.models import BaseModel


class Course(BaseModel):
    """A single entry in the college's master course catalog, e.g.
    CHE101 - Introduction to Community Health (3 units).
    """

    code = models.CharField(
        max_length=20, unique=True,
        help_text='e.g. CHE101. Must start with the parent department\'s code.',
    )
    title = models.CharField(max_length=200)
    credit_units = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(6)],
    )
    level = models.PositiveSmallIntegerField(
        choices=Level.choices, default=Level.LEVEL_100,
        help_text='The student level this course is offered to (FR-STU-05).',
    )
    department = models.ForeignKey(
        'departments.Department',
        on_delete=models.PROTECT,
        related_name='courses',
    )

    class Meta:
        verbose_name = 'Course'
        verbose_name_plural = 'Courses'
        ordering = ['code']

    def __str__(self):
        return f'{self.code} - {self.title}'

    def clean(self):
        if self.code:
            self.code = self.code.strip().upper()
        if self.code and self.department_id and not self.code.startswith(self.department.code):
            raise ValidationError({
                'code': f'Course code should start with the department code "{self.department.code}", e.g. {self.department.code}101.',
            })
