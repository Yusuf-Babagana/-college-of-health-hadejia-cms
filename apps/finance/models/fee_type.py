from django.db import models

from apps.core.models import BaseModel


class FeeType(BaseModel):
    """A billable activity the school collects money for, e.g. Tuition,
    Registration, Practical Fee, Board Exam Fee, Hostel Fee. Each fee type
    gets its own FeeStructure (and therefore its own invoice per student),
    so the Bursar can bill and track each activity separately instead of
    lumping everything into one fee.
    """

    name = models.CharField(max_length=100, unique=True)
    description = models.CharField(max_length=200, blank=True)

    class Meta:
        verbose_name = 'Fee Type'
        verbose_name_plural = 'Fee Types'
        ordering = ['name']

    def __str__(self):
        return self.name
