from django.db import models

from apps.core.models import BaseModel


class Programme(BaseModel):
    """An admission programme applicants can choose as first/second choice.

    Deliberately separate from apps.courses.Course, which represents a single
    course unit (e.g. CHE101) for already-enrolled students, not a whole
    programme/curriculum an applicant is applying into.
    """

    name = models.CharField(max_length=150, unique=True)
    short_code = models.CharField(max_length=20, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Programme'
        verbose_name_plural = 'Programmes'
        ordering = ['name']

    def __str__(self):
        return self.name
