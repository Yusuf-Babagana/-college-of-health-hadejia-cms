from django.core.exceptions import ValidationError
from django.db import models

from apps.core.constants import Level
from apps.core.models import BaseModel
from apps.core.utils.validators import matric_number_validator


class Student(BaseModel):
    """A student's academic profile, extending a User account.

    Records are created by the separate Admission portal (out of scope
    here) - this app is responsible for what happens after admission:
    status changes and the searchable student directory.
    """

    class Status(models.TextChoices):
        ACTIVE = 'active', 'Active'
        SUSPENDED = 'suspended', 'Suspended'
        WITHDRAWN = 'withdrawn', 'Withdrawn'
        GRADUATED = 'graduated', 'Graduated'

    user = models.OneToOneField(
        'accounts.User',
        on_delete=models.CASCADE,
        related_name='student_profile',
    )
    matric_number = models.CharField(
        max_length=30, unique=True, validators=[matric_number_validator],
    )
    department = models.ForeignKey(
        'departments.Department',
        on_delete=models.PROTECT,
        related_name='students',
    )
    level = models.PositiveSmallIntegerField(choices=Level.choices, default=Level.LEVEL_100)
    admission_session = models.ForeignKey(
        'academics.AcademicSession',
        on_delete=models.PROTECT,
        related_name='admitted_students',
    )
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.ACTIVE)

    class Meta:
        verbose_name = 'Student'
        verbose_name_plural = 'Students'
        ordering = ['matric_number']

    def __str__(self):
        return f'{self.matric_number} - {self.user.get_full_name() or self.user.username}'

    def clean(self):
        from apps.core.constants import Role

        if self.user_id and self.user.role != Role.STUDENT:
            raise ValidationError({'user': 'This user does not have the Student role.'})
