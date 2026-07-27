from django.db import models

from apps.core.models import BaseModel


class AdmissionPayment(BaseModel):
    """A Paystack transaction for the admission application fee."""

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        SUCCESSFUL = 'successful', 'Successful'
        FAILED = 'failed', 'Failed'

    applicant = models.ForeignKey(
        'admissions.Applicant', on_delete=models.CASCADE, related_name='payments',
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    reference = models.CharField(max_length=40, unique=True, db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    paid_at = models.DateTimeField(null=True, blank=True)
    raw_response = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = 'Admission Payment'
        verbose_name_plural = 'Admission Payments'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.reference} ({self.get_status_display()})'
