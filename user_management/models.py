import datetime

from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User
from django.conf import settings
from .managers import ExtendUserManager
from django.utils.crypto import get_random_string
from django.contrib.auth.models import AbstractUser
from django.utils.translation import gettext_lazy as _
from django.db.models import Q
from uuid import uuid1


class UserExtended(AbstractUser):
    username = None
    email = models.EmailField(_("email address"), unique=True)

    phone = models.CharField(max_length=12)
    mobile = models.CharField(max_length=12)

    is_guest = models.BooleanField(default=False)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = ExtendUserManager()

    def __str__(self):
        return self.email


class UserVerification(models.Model):
    """Base model for all verification purposes"""

    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=['email']),
        ]

    email = models.EmailField(blank=False)
    creation_timestamp = models.DateTimeField(default=timezone.now)
    expiry_timestamp = models.DateTimeField()

    def is_time_expired(self):
        """Is this entry time expired"""
        return self.expiry_timestamp < timezone.now()

    @classmethod
    def remove_expired(cls, email=None):
        """Remove all time expired entries - filtered by email"""
        qs = cls.objects.filter(expiry_timestamp__gt=timezone.now())
        if email:
            qs = qs.filter(email=email)

        qs.delete()


class RegistrationVerifier(UserVerification):
    class Meta:
        indexes = [
            models.Index(name='byUUid', fields=['uuid'])
        ]

    uuid = models.UUIDField(null=True, blank=True, default=None)

    def save(self, *args, **kwargs):
        self.uuid = uuid1()
        super().save(*args, **kwargs)

    @classmethod
    def confirm_registration_verification(cls, uuid):
        """Return the email address for this registration attempt or Raise ObjectNotFound"""
        try:
            inst: UserVerification = cls.objects.filter(type="uuid")
            return inst.email
        except cls.DoesNotExist:
            raise

    @classmethod
    def add_registration_verifier(cls, user, *args, **kwargs):
        """ Registrations have a 24 hour timeout"""
        inst = cls(user=user,
                   expiry_timestamp=timezone.now() + datetime.timedelta(hours=24))
        inst.save(*args, **kwargs)
        return inst


class GuestVerifier(UserVerification):
    """Verification for a Guest account - can have a number of retries"""

    short_code_lifetime = 60
    max_retry = 3

    class Meta:
        indexes = [
            models.Index(name='byShortCode', fields=['short_code'])
        ]

    class RejectionReason(models.TextChoices):
        expired = "expired"
        entry_error = "entry_error"

    short_code = models.CharField(null=True, blank=True, default=None, max_length=7)
    retry_count = models.IntegerField(null=False, blank=False)
    reason_code = models.CharField(choices=RejectionReason.choices, null=True, max_length=11)

    def save(self, *args, **kwargs):
        alphabet = '3456789ABCDEGHJKLMNPQRSTUVWXY'  # Exclude 0,1,2 and OIZ
        code = get_random_string(length=7, allowed_chars=alphabet)
        # Repeat until the code is unique - unlikely that we will have a collision but better safe
        while self.__class__.objects.filter(short_code=code).exclude(pk=self.pk).exists():
            code = get_random_string(length=7, allowed_chars=alphabet)
        self.short_code = code
        super().save(*args, **kwargs)

    @classmethod
    def confirm_guest_identification(cls, user, short_code):
        """Return True if this short code matches this user"""
        return cls.objects.filter(user=user, short_code=short_code).exists()

    @classmethod
    def add_guest_verifier(cls, email, *args, **kwargs):
        """Guest verification - short code lasts one hour"""
        kwargs.setdefault('expiry', timezone.now() + datetime.timedelta(minutes=cls.short_code_lifetime))
        kwargs.setdefault('retry_count', cls.max_retry)

        inst = cls(email=email,
                   expiry_timestamp=kwargs['expiry'],
                   retry_count=kwargs['retry_count'],
                   reason_code=None)
        inst.save()
        return inst


class PasswordResetApplication(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='password_resets', on_delete=models.CASCADE)
    uuid = models.UUIDField(db_index=True)
