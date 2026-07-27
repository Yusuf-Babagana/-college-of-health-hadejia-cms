from django.conf import settings
from django.db import models

from apps.core.models import BaseModel
from apps.core.utils.validators import validate_document_file, validate_image_file


class Application(BaseModel):
    """The single admission application form, filled in across five
    sections. One row per Applicant, created empty at signup.
    """

    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        SUBMITTED = 'submitted', 'Submitted'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'

    class Gender(models.TextChoices):
        MALE = 'male', 'Male'
        FEMALE = 'female', 'Female'

    applicant = models.OneToOneField(
        'admissions.Applicant', on_delete=models.CASCADE, related_name='application',
    )

    # --- Section A: personal + guardian details ---
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=10, choices=Gender.choices, blank=True)
    state_of_origin = models.CharField(max_length=100, blank=True)
    lga_of_origin = models.CharField(max_length=100, blank=True)
    home_address = models.TextField(blank=True)
    guardian_name = models.CharField(max_length=150, blank=True)
    guardian_phone = models.CharField(max_length=20, blank=True)
    guardian_address = models.TextField(blank=True)

    # --- Section D: course selection ---
    programme_first_choice = models.ForeignKey(
        'admissions.Programme', on_delete=models.PROTECT, null=True, blank=True,
        related_name='first_choice_applications',
    )
    programme_second_choice = models.ForeignKey(
        'admissions.Programme', on_delete=models.PROTECT, null=True, blank=True,
        related_name='second_choice_applications',
    )

    # --- Section E: declaration + documents ---
    passport_photo = models.ImageField(
        upload_to='admissions/passports/', null=True, blank=True, validators=[validate_image_file],
    )
    declaration_accepted = models.BooleanField(default=False)

    # --- Progress tracking ---
    section_a_complete = models.BooleanField(default=False)
    section_b_complete = models.BooleanField(default=False)
    section_c_complete = models.BooleanField(default=False)
    section_d_complete = models.BooleanField(default=False)
    section_e_complete = models.BooleanField(default=False)

    # --- Review ---
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Application'
        verbose_name_plural = 'Applications'
        ordering = ['-created_at']

    def __str__(self):
        return f'Application: {self.applicant}'

    @property
    def all_sections_complete(self):
        return all([
            self.section_a_complete,
            self.section_b_complete,
            self.section_c_complete,
            self.section_d_complete,
            self.section_e_complete,
        ])

    @property
    def completion_percent(self):
        flags = [
            self.section_a_complete, self.section_b_complete, self.section_c_complete,
            self.section_d_complete, self.section_e_complete,
        ]
        return int(100 * sum(flags) / len(flags))


class SchoolAttended(BaseModel):
    """One school in an applicant's educational history (up to 3)."""

    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name='schools_attended')
    order = models.PositiveSmallIntegerField()
    school_name = models.CharField(max_length=200)
    qualification = models.CharField(max_length=150, blank=True)
    start_year = models.PositiveIntegerField(null=True, blank=True)
    end_year = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        verbose_name = 'School Attended'
        verbose_name_plural = 'Schools Attended'
        ordering = ['order']

    def __str__(self):
        return self.school_name


class SSCESitting(BaseModel):
    """One SSCE exam sitting (up to 2) belonging to an application."""

    class ExamType(models.TextChoices):
        WAEC = 'waec', 'WAEC'
        NECO = 'neco', 'NECO'
        NABTEB = 'nabteb', 'NABTEB'

    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name='ssce_sittings')
    sitting_number = models.PositiveSmallIntegerField()
    exam_type = models.CharField(max_length=10, choices=ExamType.choices, blank=True)
    exam_year = models.PositiveIntegerField(null=True, blank=True)
    exam_number = models.CharField(max_length=50, blank=True)

    class Meta:
        verbose_name = 'SSCE Sitting'
        verbose_name_plural = 'SSCE Sittings'
        ordering = ['sitting_number']
        constraints = [
            models.UniqueConstraint(fields=['application', 'sitting_number'], name='unique_sitting_per_application'),
        ]

    def __str__(self):
        return f'Sitting {self.sitting_number} ({self.get_exam_type_display() or "-"})'


class SSCESubjectResult(BaseModel):
    """One subject/grade pair within an SSCE sitting."""

    sitting = models.ForeignKey(SSCESitting, on_delete=models.CASCADE, related_name='subject_results')
    subject_name = models.CharField(max_length=100)
    grade = models.CharField(max_length=10)

    class Meta:
        verbose_name = 'SSCE Subject Result'
        verbose_name_plural = 'SSCE Subject Results'
        ordering = ['created_at']

    def __str__(self):
        return f'{self.subject_name}: {self.grade}'


class UploadedDocument(BaseModel):
    """A supporting document attached to an application (SSCE result slip,
    birth certificate, LGA certificate, etc.) - distinct from the dedicated
    passport_photo field on Application.
    """

    class DocumentType(models.TextChoices):
        SSCE_RESULT = 'ssce_result', 'SSCE Result Slip'
        BIRTH_CERTIFICATE = 'birth_certificate', 'Birth Certificate'
        LGA_CERTIFICATE = 'lga_certificate', 'LGA Certificate of Origin'
        OTHER = 'other', 'Other'

    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name='documents')
    document_type = models.CharField(max_length=30, choices=DocumentType.choices, default=DocumentType.OTHER)
    file = models.FileField(upload_to='admissions/documents/', validators=[validate_document_file])

    class Meta:
        verbose_name = 'Uploaded Document'
        verbose_name_plural = 'Uploaded Documents'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.get_document_type_display()} - {self.application}'
