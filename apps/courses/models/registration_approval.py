from django.db import models

from apps.core.models import BaseModel


class RegistrationApproval(BaseModel):
    """Whether the HOD has signed off on a student's course registration
    for one semester. The registration itself is just the set of
    REGISTERED CourseRegistration rows for that student+semester - this
    is the separate approval gate on top of it: while pending (the
    default, including when no row exists yet), the student can freely
    add/drop their own courses; once approved, student self-service
    add/drop locks, the registration slip becomes printable, and any
    further change has to go through the HOD dashboard instead.
    """

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        APPROVED = 'approved', 'Approved'

    student = models.ForeignKey(
        'students.Student',
        on_delete=models.CASCADE,
        related_name='registration_approvals',
    )
    semester = models.ForeignKey(
        'academics.Semester',
        on_delete=models.CASCADE,
        related_name='registration_approvals',
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        'accounts.User', null=True, blank=True, on_delete=models.SET_NULL, related_name='+',
    )
    review_comment = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = 'Registration Approval'
        verbose_name_plural = 'Registration Approvals'
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['student', 'semester'],
                name='unique_approval_per_student_semester',
            ),
        ]

    def __str__(self):
        return f'{self.student.matric_number} - {self.semester} ({self.get_status_display()})'

    @property
    def is_approved(self):
        return self.status == self.Status.APPROVED
