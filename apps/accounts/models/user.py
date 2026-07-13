import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models

from apps.core.constants import Role
from apps.core.utils.validators import phone_number_validator


class User(AbstractUser):
    """Custom user model. Every account in the system - regardless of role -
    is a row in this table. Role-specific data (student profile, lecturer
    profile, etc.) lives in a OneToOne extension model owned by that app.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    role = models.CharField(max_length=20, choices=Role.choices, db_index=True)
    phone_number = models.CharField(
        max_length=15, validators=[phone_number_validator], blank=True
    )
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    must_change_password = models.BooleanField(
        default=False,
        help_text='Forces the user to set a new password on next login.',
    )
    is_active_account = models.BooleanField(
        default=True,
        help_text='Soft-disable an account without deleting it.',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'User'
        verbose_name_plural = 'Users'
        ordering = ['-date_joined']

    def __str__(self):
        return f'{self.get_full_name() or self.username} ({self.get_role_display()})'

    def get_role_display_short(self):
        return self.get_role_display()

    @property
    def is_student(self):
        return self.role == Role.STUDENT

    @property
    def is_lecturer(self):
        return self.role == Role.LECTURER

    @property
    def is_hod(self):
        return self.role == Role.HOD

    @property
    def is_registrar(self):
        return self.role == Role.REGISTRAR

    @property
    def is_bursar(self):
        return self.role == Role.BURSAR

    @property
    def is_exam_officer(self):
        return self.role == Role.EXAM_OFFICER

    @property
    def is_ict_admin(self):
        return self.role == Role.ICT_ADMIN

    @property
    def is_super_admin(self):
        return self.role == Role.SUPER_ADMIN
