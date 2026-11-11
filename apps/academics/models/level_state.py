from django.db import models

from apps.core.constants import Level
from apps.core.models import UUIDModel, TimeStampedModel


DUPLICATE_MESSAGE = (
    'A Level Semester State already exists for this Programme, Level and Semester - Session.'
)


class LevelSemesterState(UUIDModel, TimeStampedModel):
    """Which semester each student level is currently running - the
    college's cohorts move at different paces (Level 100 can be in First
    Semester while Level 200 is already in Second, possibly even in a
    different session), so a single global "active semester" is ambiguous.

    A level can hold several rows over time - one per Programme + Level +
    Semester (which carries its Academic Session) - and the CURRENT one
    is the latest semester (newest session, then Second over First). See
    academics.selectors.get_semester_for_level. Only an exact duplicate
    of Programme + Level + Semester is rejected.

    One current row per level, set by the Registrar. Everything that used to ask
    "what is THE active semester?" now asks "what semester is THIS level
    in?" - a student's current session/semester is derived from their
    level, and a course offering's semester from the course's level.

    Deliberately not a SoftDeleteModel: this is live operational state,
    not a record anyone should archive - a level with no row simply has
    no semester in progress.
    """

    level = models.PositiveSmallIntegerField(choices=Level.choices)
    # NULL = the college-wide default for this level (every row that
    # existed before per-programme states). A row with a programme
    # overrides the default for that programme only.
    programme = models.ForeignKey(
        'admissions.Programme',
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='level_states',
    )
    semester = models.ForeignKey(
        'academics.Semester',
        on_delete=models.PROTECT,
        related_name='level_states',
    )

    class Meta:
        verbose_name = 'Level Semester State'
        verbose_name_plural = 'Level Semester States'
        ordering = ['level', 'programme__name']
        # A programme + level can have many states over time (one per
        # semester/session); only the exact same programme + level +
        # semester is a duplicate. The second constraint covers the
        # college-wide default rows (programme NULL), which a plain
        # unique constraint can't catch because NULL != NULL in SQL.
        constraints = [
            models.UniqueConstraint(
                fields=['programme', 'level', 'semester'],
                name='unique_level_state_per_programme_semester',
                violation_error_message=DUPLICATE_MESSAGE,
            ),
            models.UniqueConstraint(
                fields=['level', 'semester'], condition=models.Q(programme__isnull=True),
                name='unique_default_level_state_per_semester',
                violation_error_message=DUPLICATE_MESSAGE,
            ),
        ]

    def __str__(self):
        scope = self.programme.short_code if self.programme_id else 'All programmes'
        return f'{scope} / {self.get_level_display()} -> {self.semester}'
