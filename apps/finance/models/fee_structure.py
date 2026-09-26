from django.core.exceptions import ValidationError
from django.db import models

from apps.core.constants import Level
from apps.core.models import BaseModel
from apps.core.utils.validators import validate_positive_amount


class FeeStructure(BaseModel):
    """The amount owed for a given Fee Type + Department + Level +
    Session, e.g. CHE Level 100 students pay 5,000 for the Practical Fee
    in the 2025/2026 Session. Each fee type (Tuition, Registration,
    Practical, Board Exam, etc.) is billed through its own FeeStructure,
    so the Bursar can generate a separate invoice per activity instead of
    one lump sum.

    Programme and Semester optionally narrow that further, most-specific
    -wins (same resolution style as results.GradeBand): a fee scoped to
    one Programme and/or one Semester beats the department/session-wide
    default (both blank) - e.g. Nursing's Practical fee can differ from
    Lab Tech's even within the same department, or First Semester can
    bill differently from Second. See selectors.get_fee_structure_for
    for the exact priority order.
    """

    fee_type = models.ForeignKey(
        'finance.FeeType',
        on_delete=models.PROTECT,
        related_name='fee_structures',
    )
    department = models.ForeignKey(
        'departments.Department',
        on_delete=models.PROTECT,
        related_name='fee_structures',
    )
    programme = models.ForeignKey(
        'admissions.Programme',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='fee_structures',
        help_text='Leave blank to apply to every programme in the department.',
    )
    level = models.PositiveSmallIntegerField(choices=Level.choices)
    session = models.ForeignKey(
        'academics.AcademicSession',
        on_delete=models.PROTECT,
        related_name='fee_structures',
    )
    semester = models.ForeignKey(
        'academics.Semester',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='fee_structures',
        help_text='Leave blank to apply to the whole session.',
    )
    amount = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[validate_positive_amount],
    )
    description = models.CharField(
        max_length=200, blank=True,
        help_text='e.g. Library + Sports Levy',
    )

    class Meta:
        verbose_name = 'Fee Structure'
        verbose_name_plural = 'Fee Structures'
        ordering = ['-session__name', 'department__code', 'level', 'fee_type__name']
        constraints = [
            models.UniqueConstraint(
                fields=['department', 'level', 'session', 'fee_type', 'programme', 'semester'],
                name='unique_fee_structure_per_dept_level_session_type_programme_semester',
            ),
        ]

    def clean(self):
        # The UniqueConstraint above can't catch two rows that both leave
        # programme/semester blank - NULL is never equal to NULL in a SQL
        # unique constraint, so the common "department/session-wide
        # default" case (both blank) needs the same Python-level check
        # GradeBand uses for its own department/programme scoping.
        conflicting = FeeStructure.objects.exclude(pk=self.pk).filter(
            department=self.department_id, level=self.level, session=self.session_id,
            fee_type=self.fee_type_id, programme=self.programme_id, semester=self.semester_id,
        )
        if conflicting.exists():
            raise ValidationError(
                'A fee structure already exists for this exact department/level/session/'
                'fee type/programme/semester combination.'
            )

    def __str__(self):
        scope = ''
        if self.programme_id:
            scope += f' [{self.programme.short_code}]'
        if self.semester_id:
            scope += f' [{self.semester.get_name_display()}]'
        return (
            f'{self.department.code} {self.level}L - {self.fee_type.name} '
            f'({self.session.name}){scope}: ₦{self.amount:,.2f}'
        )
