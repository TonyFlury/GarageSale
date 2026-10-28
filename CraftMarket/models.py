"""Pitch fee records and upload-path compatibility for historical migrations.

Active trader data lives in Contributors.models. Historical migrations reconstruct
the old models themselves, but still reference this upload callable by import path.
"""
from django.utils.text import slugify
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone
from decimal import Decimal


def save_logo_to(instance, file_name: str) -> str:
    return f'marketeer_{instance.event.event_date.year}/{slugify(instance.trading_name)}_{file_name}'


class PitchPayment(models.Model):
    """A recorded pitch fee, retained independently of later booking statuses."""
    contributor = models.ForeignKey('Contributors.Contributor', on_delete=models.PROTECT)
    event = models.ForeignKey('GarageSale.EventData', on_delete=models.PROTECT)
    status_record = models.OneToOneField('Contributors.ContributorEvent', on_delete=models.PROTECT)
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    paid_on = models.DateField()
    reference = models.CharField(max_length=254, blank=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    recorded_at = models.DateTimeField(default=timezone.now)

    class Meta:
        default_permissions = ('view',)
        permissions = [
            ('record_pitch_payment', 'Can record market pitch fee payments'),
            ('cancel_market_booking', 'Can cancel unpaid market bookings'),
            ('reinstate_market_booking', 'Can reinstate cancelled market bookings'),
        ]
        constraints = [
            models.UniqueConstraint(fields=['contributor', 'event'], name='unique_market_pitch_payment'),
            models.CheckConstraint(check=models.Q(amount__gt=0), name='market_pitch_payment_positive'),
        ]
