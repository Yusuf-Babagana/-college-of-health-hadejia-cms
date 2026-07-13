from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core.models import BaseModel


class GradeBand(BaseModel):
    """A configurable grading scale band, e.g. 70-100 = A = 5.00 points.
    Exam Officer manages these; Grade looks up its letter/point from here
    rather than hardcoding a scale in Python.
    """

    min_score = models.PositiveSmallIntegerField(validators=[MaxValueValidator(100)])
    max_score = models.PositiveSmallIntegerField(validators=[MaxValueValidator(100)])
    letter = models.CharField(max_length=2)
    grade_point = models.DecimalField(max_digits=3, decimal_places=2, validators=[MinValueValidator(0)])

    class Meta:
        verbose_name = 'Grade Band'
        verbose_name_plural = 'Grade Bands'
        ordering = ['-min_score']

    def __str__(self):
        return f'{self.letter} ({self.min_score}-{self.max_score}) = {self.grade_point}'

    def clean(self):
        if self.min_score > self.max_score:
            raise ValidationError({'max_score': 'Max score must be greater than or equal to min score.'})

        overlapping = GradeBand.objects.exclude(pk=self.pk).filter(
            min_score__lte=self.max_score, max_score__gte=self.min_score,
        )
        if overlapping.exists():
            raise ValidationError('This score range overlaps with an existing grade band.')
