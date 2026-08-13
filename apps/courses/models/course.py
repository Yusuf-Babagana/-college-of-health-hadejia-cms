from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core.constants import Level, SemesterName
from apps.core.models import BaseModel


class Course(BaseModel):
    """A single entry in the college's master course catalog, e.g.
    CHE101 - Introduction to Community Health (3 units).
    """

    code = models.CharField(
        max_length=20, unique=True,
        help_text='e.g. CHE101.',
    )
    title = models.CharField(max_length=200)
    credit_units = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(6)],
    )
    level = models.PositiveSmallIntegerField(
        choices=Level.choices, default=Level.LEVEL_100,
        help_text='The student level this course is offered to (FR-STU-05).',
    )
    semester_name = models.CharField(
        max_length=10, choices=SemesterName.choices, default=SemesterName.FIRST,
        help_text='Which semester this course is normally taught in - a Course '
                   'Offering for this course can only be created in a matching semester.',
    )
    department = models.ForeignKey(
        'departments.Department',
        on_delete=models.PROTECT,
        related_name='courses',
    )
    programme = models.ForeignKey(
        'admissions.Programme',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='courses',
        help_text='The programme (within the department) this course belongs to, if any.',
    )
    eligible_departments = models.ManyToManyField(
        'departments.Department',
        blank=True,
        related_name='cross_listed_courses',
        help_text='Extra departments (besides this course\'s own Department above) whose '
                   'students may also register for it - e.g. a General Studies course taken '
                   'by several departments. Leave blank for an ordinary single-department course.',
    )
    eligible_programmes = models.ManyToManyField(
        'admissions.Programme',
        blank=True,
        related_name='cross_listed_courses',
        help_text='Extra programmes (besides this course\'s own Programme above) whose '
                   'students may also register for it. Leave blank for an ordinary course.',
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
