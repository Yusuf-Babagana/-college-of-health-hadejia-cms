from django.core.exceptions import ValidationError
from django.db import models

from apps.core.constants import SemesterName
from apps.core.models import BaseModel


DUPLICATE_MESSAGE = (
    'A semester already exists for this Programme, Academic Session and Semester name.'
)


class Semester(BaseModel):
    """A semester within an academic session. There is no single globally
    "active" semester - each student level runs its own current semester,
    tracked in LevelSemesterState, since cohorts move at different paces
    (Level 100 can be in First Semester while Level 200 is in Second).
    """

    # Kept as an attribute for backward compatibility with any code/templates
    # referencing Semester.SemesterName - the canonical definition now lives
    # in apps.core.constants so courses.Course can share the same choices.
    SemesterName = SemesterName

    session = models.ForeignKey(
        'academics.AcademicSession',
        on_delete=models.PROTECT,
        related_name='semesters',
    )
    # The programme this semester was created for. NULL on every semester
    # that existed before programmes were attached (college-wide); the
    # create/edit forms require it for anything saved from now on.
    programme = models.ForeignKey(
        'admissions.Programme',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='semesters',
    )
    name = models.CharField(max_length=10, choices=SemesterName.choices)
    registration_start = models.DateTimeField(
        null=True, blank=True,
        help_text='When course registration opens for this semester.',
    )
    registration_end = models.DateTimeField(
        null=True, blank=True,
        help_text='When course registration closes for this semester.',
    )

    class Meta:
        verbose_name = 'Semester'
        verbose_name_plural = 'Semesters'
        ordering = ['-session__name', 'name']
        # One semester per Programme + Session + Name. Different programmes
        # may each have, say, a First Semester in the same session. The
        # second constraint covers semesters with no programme (those
        # created before programmes were attached), which the first can't
        # catch because NULL != NULL in SQL.
        constraints = [
            models.UniqueConstraint(
                fields=['programme', 'session', 'name'],
                name='unique_semester_per_programme_session',
                violation_error_message=DUPLICATE_MESSAGE,
            ),
            models.UniqueConstraint(
                fields=['session', 'name'], condition=models.Q(programme__isnull=True),
                name='unique_default_semester_per_session',
                violation_error_message=DUPLICATE_MESSAGE,
            ),
        ]

    def __str__(self):
        # The programme code keeps same-named semesters of different
        # programmes distinguishable in every dropdown and list.
        label = f'{self.get_name_display()} - {self.session.name}'
        return f'{label} [{self.programme.short_code}]' if self.programme_id else label

    def clean(self):
        if self.programme_id and self.session_id and not self.session.applies_to(self.programme_id):
            raise ValidationError({
                'session': f'{self.session} is not an academic session for {self.programme}.',
            })
        if self.registration_start and self.registration_end and self.registration_end <= self.registration_start:
            raise ValidationError({'registration_end': 'Registration close date must be after the open date.'})

    def unique_error_message(self, model_class, unique_check):
        # Forms and the admin ask the model for its duplicate message; give
        # them ours instead of Django's generic "...already exists".
        if set(unique_check) in ({'programme', 'session', 'name'}, {'session', 'name'}):
            return ValidationError(DUPLICATE_MESSAGE, code='unique_together')
        return super().unique_error_message(model_class, unique_check)

    @property
    def is_registration_open(self):
        if not (self.registration_start and self.registration_end):
            return False
        from django.utils import timezone
        now = timezone.now()
        return self.registration_start <= now <= self.registration_end
