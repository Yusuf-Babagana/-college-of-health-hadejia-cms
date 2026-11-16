from django.db import models

from apps.core.models import TimeStampedModel, UUIDModel
from apps.core.utils.validators import phone_number_validator


class Guardian(UUIDModel, TimeStampedModel):
    """The student's parent / guardian / next of kin - who the college
    contacts about the student. One per student; the student fills it in
    from their profile page.
    """

    class Relationship(models.TextChoices):
        FATHER = 'father', 'Father'
        MOTHER = 'mother', 'Mother'
        BROTHER = 'brother', 'Brother'
        SISTER = 'sister', 'Sister'
        UNCLE = 'uncle', 'Uncle'
        AUNT = 'aunt', 'Aunt'
        SPOUSE = 'spouse', 'Spouse'
        GUARDIAN = 'guardian', 'Legal Guardian'
        OTHER = 'other', 'Other'

    student = models.OneToOneField(
        'students.Student', on_delete=models.CASCADE, related_name='guardian',
    )
    full_name = models.CharField(max_length=150)
    relationship = models.CharField(max_length=10, choices=Relationship.choices)
    phone_number = models.CharField(max_length=15, validators=[phone_number_validator])
    email = models.EmailField(blank=True)
    occupation = models.CharField(max_length=120, blank=True)
    address = models.TextField()

    class Meta:
        verbose_name = 'Guardian'
        verbose_name_plural = 'Guardians'

    def __str__(self):
        return f'{self.full_name} ({self.get_relationship_display()}) - {self.student.matric_number}'
