from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.core.models import BaseModel


class Lecturer(BaseModel):
    """Academic staff profile, extending a User account with department
    assignment and qualifications. Only users with role=lecturer should
    have one of these (enforced in the form/service layer, not just here).
    """

    user = models.OneToOneField(
        'accounts.User',
        on_delete=models.CASCADE,
        related_name='lecturer_profile',
    )
    department = models.ForeignKey(
        'departments.Department',
        on_delete=models.PROTECT,
        related_name='lecturers',
    )
    qualification = models.CharField(max_length=150, blank=True, help_text='e.g. PhD Public Health')
    specialization = models.CharField(max_length=150, blank=True)
    appointment_date = models.DateField(default=timezone.now)

    class Meta:
        verbose_name = 'Lecturer'
        verbose_name_plural = 'Lecturers'
        ordering = ['user__first_name', 'user__last_name']

    def __str__(self):
        return f'{self.user.get_full_name() or self.user.username} - {self.department.code}'

    def clean(self):
        from apps.core.constants import Role

        # HOD is allowed too: a department head is promoted from Lecturer
        # to HOD by apps.departments.services.assign_hod without losing
        # their underlying Lecturer profile.
        if self.user_id and self.user.role not in (Role.LECTURER, Role.HOD):
            raise ValidationError({'user': 'This user does not have the Lecturer role.'})
