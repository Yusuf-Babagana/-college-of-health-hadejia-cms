from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core.models import BaseModel


class Programme(BaseModel):
    """A programme of study offered by a department, e.g. Community
    Health's "Diploma in Community Health" or "Certificate in Community
    Health (JCHEW)". Applicants choose one as their first/second choice
    on the admission form; once admitted, a Student and the Courses
    built for their track are tagged with the same Programme, scoped
    under their Department.

    Deliberately separate from apps.courses.Course, which represents a
    single course unit (e.g. CHE101), not a whole curriculum.

    ``department`` is nullable so existing Programme rows (and any
    created before their department is known) don't block on a value -
    fill it in via the Programme admin/edit screen when ready.
    """

    name = models.CharField(max_length=150, unique=True)
    short_code = models.CharField(max_length=20, unique=True)
    department = models.ForeignKey(
        'departments.Department',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='programmes',
    )
    duration_levels = models.PositiveSmallIntegerField(
        default=4,
        validators=[MinValueValidator(1), MaxValueValidator(6)],
        help_text='How many levels this programme runs, starting from 100 Level - e.g. a '
                   '2-year Certificate is 2 (100 & 200 Level only); a 3-year Diploma is 3 '
                   '(100-300 Level); a full 4-year programme is 4. Drives the Level/Semester '
                   'breakdown shown under this programme on the HOD dashboard and course allocation.',
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Programme'
        verbose_name_plural = 'Programmes'
        ordering = ['name']

    def __str__(self):
        return self.name

    @property
    def levels(self):
        """The Level values (100, 200, ...) this programme actually
        spans, e.g. a 2-level Certificate -> [100, 200].
        """
        from apps.core.constants import Level

        return [value for value, _ in Level.choices][:self.duration_levels]
