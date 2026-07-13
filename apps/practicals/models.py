from django.db import models

from apps.core.models import BaseModel


class PracticalPlacement(BaseModel):
    """One row on the Practical Coordinator's placement sheet, created for
    a student once they've paid a Practical fee invoice. Surname, first
    name, registration number, and phone are read live from the student's
    profile wherever this is displayed/exported rather than copied in, so
    a later correction to the student record is always reflected; the
    fields that live here (other names, cadre, state/LGA of practical)
    have no home anywhere else in the system and are the Coordinator's
    to fill in.

    Tied to the specific Invoice (not just the student) so a Practical
    fee billed again in a later session gets its own placement row -
    where a student did their last round of practicals shouldn't leak
    into the next one.
    """

    invoice = models.OneToOneField(
        'finance.Invoice',
        on_delete=models.CASCADE,
        related_name='practical_placement',
    )
    student = models.ForeignKey(
        'students.Student',
        on_delete=models.CASCADE,
        related_name='practical_placements',
    )
    other_names = models.CharField(
        max_length=100, blank=True,
        help_text='Middle name(s), if any - shown as OTHERNAMES on the sheet.',
    )
    cadre = models.CharField(max_length=50, blank=True)
    state_of_practical = models.CharField(max_length=50, blank=True)
    lga_of_practical = models.CharField(max_length=50, blank=True)

    class Meta:
        verbose_name = 'Practical Placement'
        verbose_name_plural = 'Practical Placements'
        ordering = ['student__matric_number']

    def __str__(self):
        return f'Practical placement - {self.student.matric_number}'

    @property
    def is_complete(self):
        return bool(self.cadre and self.state_of_practical and self.lga_of_practical)
