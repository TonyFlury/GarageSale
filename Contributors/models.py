import datetime
from datetime import UTC
from decimal import Decimal, InvalidOperation
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError

import django.utils.timezone
from django.db import models

from GarageSale.models import EventData
from django.utils.text import slugify

# Only contributor name and type are required; contact and other details are optional.

def save_logo_to(instance, file_name: str) -> str:
    return f'contributors/{slugify(instance.contributor_name)}_{file_name}'

# Create your models here.
class Contributor(models.Model):
    contributor_type = models.CharField(max_length=30, null=False, blank=False)
    contributor_name = models.CharField(max_length=120, null=False, blank=False)
    contact_name: str = models.CharField(max_length=120, blank=True)
    phone = models.CharField(max_length=12, blank=True)
    description = models.TextField(max_length=1000, blank=True)
    icon: str = models.ImageField(upload_to=save_logo_to, null=True, blank=True)
    email: str = models.EmailField(max_length=254, null=True, blank=True)
    socials: str = models.JSONField(null=True, blank=True)
    is_hidden = models.BooleanField(default=False, db_index=True)
    hidden_reason = models.TextField(max_length=1000, blank=True)
    hidden_at = models.DateTimeField(null=True, blank=True)
    hidden_by = models.ForeignKey('user_management.UserExtended', on_delete=models.SET_NULL,
                                  null=True, blank=True, related_name='hidden_contributors')

    class Meta:
        permissions = [
            ('hide_sponsor', 'Can hide and restore sponsors'),
            ('delete_sponsor', 'Can delete unused sponsors'),
            ('hide_marketer', 'Can hide and restore market traders'),
            ('delete_marketer', 'Can delete unused market traders'),
        ]
    def __str__(self):
        return self.contributor_name


# This tracks activity on this contributor for a given 'campaign event' ...
class ContributorEvent(models.Model):
    contributor = models.ForeignKey(Contributor, on_delete=models.CASCADE)
    event = models.ForeignKey(EventData, on_delete=models.CASCADE)
    status = models.CharField(max_length=20, null=True, blank=True) # status is dependent on the data type
    details = models.TextField(max_length=1000, blank=True)
    timestamp = models.DateTimeField(default=django.utils.timezone.now)
    user = models.ForeignKey('user_management.UserExtended', on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        return f'{self.contributor} - {self.event} - {self.status} @ {self.timestamp}'

# Actual category and event_type entirely depends on the contributor type
# This tracks things like creation, modifications etc.
class ContributorHistory(models.Model):
    contributor = models.ForeignKey(Contributor, on_delete=models.CASCADE)
    event_category = models.CharField(max_length=10, null=True, blank=True)
    event_type = models.CharField(max_length=10, null=True, blank=True)
    related_event = models.ForeignKey(EventData, on_delete=models.CASCADE, null=True, blank=True)
    details = models.TextField(max_length=1000, null=True, blank=True)
    timestamp = models.DateTimeField(default=django.utils.timezone.now)
    user = models.ForeignKey('user_management.UserExtended', on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        return f'{self.contributor} - [{self.event_category}]-{self.event_type} @ {self.timestamp}'

class Contributions(models.Model):
    class Classification(models.TextChoices):
        UNCLASSIFIED = "unclassified", "Unclassified"
        PRIZE_DRAW = "prize_draw", "Prize Draw"
        TOMBOLA = "tombola", "Tombola"

    contributor = models.ForeignKey(Contributor, on_delete=models.PROTECT)
    event = models.ForeignKey(EventData, on_delete=models.CASCADE, null=True, blank=True)
    gift = models.TextField(max_length=1000, null=True, blank=True)
    cash = models.BooleanField(default=False)
    amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True,
                                 validators=[MinValueValidator(Decimal('0'))])
    classification = models.CharField(max_length=12, choices=Classification.choices, default=Classification.UNCLASSIFIED)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        permissions = [
            ('view_prize_allocation', 'Can view prize allocation'),
            ('change_prize_allocation', 'Can categorise and order prizes'),
        ]
        constraints = [models.CheckConstraint(check=models.Q(amount__gte=0) | models.Q(amount__isnull=True),
                                              name='contribution_amount_nonnegative')]

    def clean(self):
        super().clean()
        if self.cash and (self.amount is None or self.amount <= 0):
            raise ValidationError({'amount': 'Enter a positive cash amount in £.'})
        if not self.cash and not (self.gift or '').strip():
            raise ValidationError({'gift': 'Describe the non-cash contribution.'})

    @property
    def monetary_value(self):
        if self.amount is not None:
            return self.amount
        # Support historical cash entries and older import/seed code using gift text.
        if self.cash:
            try:
                value = Decimal((self.gift or '').strip().removeprefix('£').replace(',', '').strip())
                if value.is_finite() and value >= 0:
                    return value
            except InvalidOperation:
                pass
        return None
