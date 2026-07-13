from decimal import Decimal

from django.db import models

from apps.core.models import BaseModel


class Invoice(BaseModel):
    """A student's bill against a specific fee structure. amount_due is a
    snapshot of the fee structure's amount at generation time, so a later
    change to FeeStructure.amount never rewrites history for invoices
    already issued.
    """

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        PARTIALLY_PAID = 'partially_paid', 'Partially Paid'
        PAID = 'paid', 'Paid'

    student = models.ForeignKey(
        'students.Student',
        on_delete=models.CASCADE,
        related_name='invoices',
    )
    fee_structure = models.ForeignKey(
        'finance.FeeStructure',
        on_delete=models.PROTECT,
        related_name='invoices',
    )
    amount_due = models.DecimalField(max_digits=12, decimal_places=2)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    issued_date = models.DateField(auto_now_add=True)
    due_date = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name = 'Invoice'
        verbose_name_plural = 'Invoices'
        ordering = ['-issued_date']
        constraints = [
            models.UniqueConstraint(
                fields=['student', 'fee_structure'],
                name='unique_invoice_per_student_fee_structure',
            ),
        ]

    def __str__(self):
        return f'{self.student.matric_number} - {self.fee_structure}'

    @property
    def balance(self):
        return self.amount_due - self.amount_paid

    @property
    def is_overdue(self):
        if not self.due_date or self.status == self.Status.PAID:
            return False
        from django.utils import timezone
        return timezone.now().date() > self.due_date

    def recompute_status(self):
        if self.amount_paid <= 0:
            self.status = self.Status.PENDING
        elif self.amount_paid < self.amount_due:
            self.status = self.Status.PARTIALLY_PAID
        else:
            self.status = self.Status.PAID
