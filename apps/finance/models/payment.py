from django.db import models

from apps.core.models import BaseModel
from apps.core.utils.validators import validate_positive_amount


class Payment(BaseModel):
    """A single payment against an invoice - either recorded offline by
    the Bursar (bank teller) or made online through Paystack.
    """

    class Method(models.TextChoices):
        OFFLINE = 'offline', 'Offline (Bank Teller)'
        ONLINE = 'online', 'Online (Paystack)'

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        SUCCESSFUL = 'successful', 'Successful'
        FAILED = 'failed', 'Failed'

    invoice = models.ForeignKey(
        'finance.Invoice',
        on_delete=models.CASCADE,
        related_name='payments',
    )
    amount = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[validate_positive_amount],
    )
    method = models.CharField(max_length=10, choices=Method.choices)
    reference = models.CharField(max_length=100, unique=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    paid_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.ForeignKey(
        'accounts.User',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='verified_payments',
        help_text='Who recorded/verified this payment. Blank for auto-verified online payments.',
    )
    notes = models.CharField(max_length=255, blank=True, help_text='e.g. bank name and teller number')

    class Meta:
        verbose_name = 'Payment'
        verbose_name_plural = 'Payments'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.reference} - {self.invoice.student.matric_number} - {self.amount}'
