from django.core.exceptions import ValidationError
from django.db import models

from apps.core.constants import Level
from apps.core.models import BaseModel


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
        max_length=30, unique=True,
        help_text='Assigned by the Registrar - no fixed format, but must be unique.',
    )
    department = models.ForeignKey(
        'departments.Department',
        on_delete=models.PROTECT,
        related_name='students',
    )
    programme = models.ForeignKey(
        'admissions.Programme',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='students',
        help_text='The programme (within the department) this student is enrolled in, if any.',
    )
    level = models.PositiveSmallIntegerField(choices=Level.choices, default=Level.LEVEL_100)

    # --- Personal profile (filled in by the student; every field optional
    # at the database level because students existed before these did) ---
    class Gender(models.TextChoices):
        MALE = 'male', 'Male'
        FEMALE = 'female', 'Female'

    class MaritalStatus(models.TextChoices):
        SINGLE = 'single', 'Single'
        MARRIED = 'married', 'Married'
        DIVORCED = 'divorced', 'Divorced'
        WIDOWED = 'widowed', 'Widowed'

    class Religion(models.TextChoices):
        ISLAM = 'islam', 'Islam'
        CHRISTIANITY = 'christianity', 'Christianity'
        OTHER = 'other', 'Other'

    class BloodGroup(models.TextChoices):
        A_POS = 'A+', 'A+'
        A_NEG = 'A-', 'A-'
        B_POS = 'B+', 'B+'
        B_NEG = 'B-', 'B-'
        AB_POS = 'AB+', 'AB+'
        AB_NEG = 'AB-', 'AB-'
        O_POS = 'O+', 'O+'
        O_NEG = 'O-', 'O-'

    class Genotype(models.TextChoices):
        AA = 'AA', 'AA'
        AS = 'AS', 'AS'
        SS = 'SS', 'SS'
        AC = 'AC', 'AC'
        SC = 'SC', 'SC'

    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=10, choices=Gender.choices, blank=True)
    marital_status = models.CharField(max_length=10, choices=MaritalStatus.choices, blank=True)
    nationality = models.CharField(max_length=60, blank=True)
    state_of_origin = models.CharField(max_length=100, blank=True)
    lga_of_origin = models.CharField('LGA of origin', max_length=100, blank=True)
    religion = models.CharField(max_length=15, choices=Religion.choices, blank=True)
    home_address = models.TextField(blank=True)
    blood_group = models.CharField(max_length=3, choices=BloodGroup.choices, blank=True)
    genotype = models.CharField(max_length=2, choices=Genotype.choices, blank=True)
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
