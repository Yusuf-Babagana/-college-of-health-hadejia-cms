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
    level = models.PositiveSmallIntegerField(choices=Level.choices)
    session = models.ForeignKey(
        'academics.AcademicSession',
        on_delete=models.PROTECT,
        related_name='fee_structures',
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
                fields=['department', 'level', 'session', 'fee_type'],
                name='unique_fee_structure_per_dept_level_session_type',
            ),
        ]

    def __str__(self):
        return (
            f'{self.department.code} {self.level}L - {self.fee_type.name} '
            f'({self.session.name}): ₦{self.amount:,.2f}'
        )
