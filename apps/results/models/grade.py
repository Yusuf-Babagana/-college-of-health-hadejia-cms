from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core.models import BaseModel


class Grade(BaseModel):
    """A student's CA + Exam score for one course offering, moving
    through a strict review pipeline: a lecturer enters and submits it,
    only the HOD can approve/reject a submitted grade, and only the Exam
    Officer can publish an approved grade. Editable only while
    Draft/Rejected - "grades become read-only after submission".
    """

    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        SUBMITTED = 'submitted', 'Submitted'
        APPROVED = 'approved', 'Approved by HOD'
        REJECTED = 'rejected', 'Rejected by HOD'
        PUBLISHED = 'published', 'Published'

    course_offering = models.ForeignKey(
        'courses.CourseOffering',
        on_delete=models.CASCADE,
        related_name='grades',
    )
    student = models.ForeignKey(
        'students.Student',
        on_delete=models.CASCADE,
        related_name='grades',
    )
    ca1_score = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('0.00'),
        validators=[MinValueValidator(0), MaxValueValidator(15)],
        help_text='First continuous assessment, out of 15.',
    )
    ca2_score = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('0.00'),
        validators=[MinValueValidator(0), MaxValueValidator(15)],
        help_text='Second continuous assessment, out of 15.',
    )
    exam_score = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('0.00'),
        validators=[MinValueValidator(0), MaxValueValidator(70)],
        help_text='Examination score, out of 70.',
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        'accounts.User', null=True, blank=True, on_delete=models.SET_NULL, related_name='+',
    )
    review_comment = models.CharField(max_length=255, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Grade'
        verbose_name_plural = 'Grades'
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['course_offering', 'student'], name='unique_grade_per_student_offering'),
        ]

    def __str__(self):
        return f'{self.student.matric_number} - {self.course_offering}'

    @property
    def ca_score(self):
        """Combined CA1 + CA2, out of 30 - kept as a read-only property so
        anything computing off the total (grade_band, broadsheets, admin
        list_display) doesn't need to know about the CA1/CA2 split.
        """
        return self.ca1_score + self.ca2_score

    @property
    def total_score(self):
        return self.ca_score + self.exam_score

    @property
    def grade_band(self):
        from .grade_band import GradeBand

        total = self.total_score
        return GradeBand.objects.filter(min_score__lte=total, max_score__gte=total).first()

    @property
    def letter_grade(self):
        band = self.grade_band
        return band.letter if band else None

    @property
    def grade_point(self):
        band = self.grade_band
        return band.grade_point if band else None

    @property
    def is_editable(self):
        return self.status in (self.Status.DRAFT, self.Status.REJECTED)
