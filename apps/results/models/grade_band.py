from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core.models import BaseModel


class GradeBand(BaseModel):
    """A configurable grading scale band, e.g. 70-100 = A = 5.00 points.
    Exam Officer manages these; Grade looks up its letter/point from here
    rather than hardcoding a scale in Python.

    Scoped by department/programme, most-specific-wins:
      - department AND programme set -> applies only to students in that
        programme.
      - department set, programme blank -> applies to every student in
        that department who has no more specific programme band.
      - both blank -> the college-wide default scale, used by any
        student whose department/programme has no override of its own.
    department/programme are independent fields, never cross-checked
    against each other (e.g. programme.department) - Programme.department
    is unreliable/NULL on most real rows in this system (see
    apps.admissions.models.Programme), so the Exam Officer picks both
    explicitly rather than one being inferred from the other.
    """

    department = models.ForeignKey(
        'departments.Department',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='grade_bands',
        help_text='Leave blank for a college-wide default band.',
    )
    programme = models.ForeignKey(
        'admissions.Programme',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='grade_bands',
        help_text='Leave blank to apply to every programme in the department (or college-wide if Department is also blank).',
    )
    min_score = models.PositiveSmallIntegerField(validators=[MaxValueValidator(100)])
    max_score = models.PositiveSmallIntegerField(validators=[MaxValueValidator(100)])
    letter = models.CharField(max_length=2)
    grade_point = models.DecimalField(max_digits=3, decimal_places=2, validators=[MinValueValidator(0)])

    class Meta:
        verbose_name = 'Grade Band'
        verbose_name_plural = 'Grade Bands'
        ordering = ['-min_score']

    def __str__(self):
        scope = self.programme.name if self.programme_id else (self.department.code if self.department_id else 'College-wide')
        return f'{self.letter} ({self.min_score}-{self.max_score}) = {self.grade_point} [{scope}]'

    def clean(self):
        if self.min_score > self.max_score:
            raise ValidationError({'max_score': 'Max score must be greater than or equal to min score.'})

        if self.programme_id and not self.department_id:
            raise ValidationError({'department': 'Select the department this programme belongs to.'})

        # Two bands only conflict if they'd apply to the same students -
        # a programme-specific band is allowed to overlap a department-
        # wide or college-wide band, since the more specific one wins
        # (see Grade.grade_band). Grade.grade_band resolves a programme
        # band by programme_id alone, ignoring department entirely, so
        # the overlap scope here has to match that: once programme is
        # set, department is just required metadata (see the check
        # above) and must NOT be part of the conflict scope, or two
        # programme bands recorded under different departments would
        # pass validation while still racing each other at resolution
        # time. Only when programme is blank does department define the
        # scope (department-wide vs college-wide default).
        scope = {'programme': self.programme_id}
        if not self.programme_id:
            scope['department'] = self.department_id
        overlapping = GradeBand.objects.exclude(pk=self.pk).filter(
            min_score__lte=self.max_score, max_score__gte=self.min_score, **scope,
        )
        if overlapping.exists():
            raise ValidationError('This score range overlaps with an existing grade band in the same scope.')
