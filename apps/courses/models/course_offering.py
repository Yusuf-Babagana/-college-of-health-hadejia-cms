from django.core.validators import MinValueValidator
from django.db import models

from apps.core.models import BaseModel


class CourseOffering(BaseModel):
    """A course actually being taught in a given semester - the HOD's
    "Assign Courses" action creates these, linking the master Course
    Catalog entry to a semester and (optionally) a lecturer. Students
    register against a CourseOffering, not the raw Course.
    """

    course = models.ForeignKey(
        'courses.Course',
        on_delete=models.PROTECT,
        related_name='offerings',
    )
    semester = models.ForeignKey(
        'academics.Semester',
        on_delete=models.PROTECT,
        related_name='course_offerings',
    )
    lecturer = models.ForeignKey(
        'lecturers.Lecturer',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='course_offerings',
    )
    capacity = models.PositiveIntegerField(default=50, validators=[MinValueValidator(1)])

    class Meta:
        verbose_name = 'Course Offering'
        verbose_name_plural = 'Course Offerings'
        ordering = ['-semester__session__name', 'course__code']
        constraints = [
            models.UniqueConstraint(fields=['course', 'semester'], name='unique_offering_per_course_semester'),
        ]

    def __str__(self):
        return f'{self.course.code} ({self.semester})'

    @property
    def registered_count(self):
        return self.registrations.filter(status='registered').count()

    @property
    def is_full(self):
        return self.registered_count >= self.capacity
