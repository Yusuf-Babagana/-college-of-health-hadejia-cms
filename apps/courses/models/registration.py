from django.db import models

from apps.core.models import BaseModel


class CourseRegistration(BaseModel):
    """A student's registration against a CourseOffering. Dropping a
    course doesn't delete this row - it flips status to DROPPED, so
    re-registering later reactivates the same row instead of violating
    the unique constraint, and the drop is still visible in history.
    """

    class Status(models.TextChoices):
        REGISTERED = 'registered', 'Registered'
        DROPPED = 'dropped', 'Dropped'

    student = models.ForeignKey(
        'students.Student',
        on_delete=models.CASCADE,
        related_name='course_registrations',
    )
    course_offering = models.ForeignKey(
        'courses.CourseOffering',
        on_delete=models.CASCADE,
        related_name='registrations',
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.REGISTERED)

    class Meta:
        verbose_name = 'Course Registration'
        verbose_name_plural = 'Course Registrations'
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['student', 'course_offering'],
                name='unique_registration_per_student_offering',
            ),
        ]

    def __str__(self):
        return f'{self.student.matric_number} - {self.course_offering}'
