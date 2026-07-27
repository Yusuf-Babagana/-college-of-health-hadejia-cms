from django.conf import settings
from django.db import models

from apps.core.models import BaseModel


class Applicant(BaseModel):
    """Extends a Role.APPLICANT user with admissions-portal-specific state.

    Created immediately at signup, alongside an empty Application row, so
    every later admissions view can assume both already exist.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='applicant_profile',
    )
    has_paid = models.BooleanField(default=False)
    payment_verified_at = models.DateTimeField(null=True, blank=True)
    referral_code_used = models.ForeignKey(
        'admissions.ReferralCode', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+',
    )

    class Meta:
        verbose_name = 'Applicant'
        verbose_name_plural = 'Applicants'
        ordering = ['-created_at']

    def __str__(self):
        return self.user.get_full_name() or self.user.email or self.user.username


class ReferralCode(BaseModel):
    """A code that waives the application fee for whoever redeems it first."""

    code = models.CharField(max_length=20, unique=True, db_index=True)
    batch_label = models.CharField(max_length=100, blank=True)
    used_by = models.ForeignKey(
        Applicant, on_delete=models.SET_NULL, null=True, blank=True, related_name='redeemed_referral_codes',
    )
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Referral Code'
        verbose_name_plural = 'Referral Codes'
        ordering = ['-created_at']

    def __str__(self):
        return self.code

    @property
    def is_used(self):
        return self.used_by_id is not None
