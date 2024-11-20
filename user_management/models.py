import datetime

from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User
from .managers import ExtendUserManager
from django.utils.crypto import get_random_string
from django.contrib.auth.models import AbstractUser
from django.utils.translation import gettext_lazy as _
from django.db import transaction
from uuid import uuid1
from django.shortcuts import reverse
from django.utils.html import escape

class UserExtended(AbstractUser):
    username = None
    email = models.EmailField(_("email address"), unique=True)

    phone = models.CharField(max_length=12)

    is_guest = models.BooleanField(default=False)

    is_verified = models.BooleanField(default=False)

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
    registration_lifetime = 24 * 60

    class Meta:
        indexes = [
            models.Index(name='byUUid', fields=['uuid'])
        ]

    uuid = models.UUIDField(null=True, blank=True, default=None)

    def link_url(self, request, next_url, site_base=None):
        if request:
            return (request.build_absolute_uri(
                location=reverse("user_management:verify", kwargs={"uuid": self.uuid})) +
                   "?" + escape(f'next={next_url}'))
        elif not request and site_base:
            relative_url = reverse("user_management:verify", kwargs={"uuid":self.uuid})
            return f'{site_base}{relative_url}?next={next_url}'
        else:
            raise NotImplementedError('Need either a request or a site base')

    def save(self, *args, **kwargs):
        self.uuid = uuid1()
        super().save(*args, **kwargs)
        return self

    @classmethod
    def confirm_registration_verification(cls, uuid):
        """Return the email address for this registration attempt or Raise ObjectNotFound"""
        try:
            inst: UserVerification = cls.objects.filter(uuid=uuid)
            return inst.email
        except cls.DoesNotExist:
            raise

    @classmethod
    def add_registration_verifier(cls, user, *args, **kwargs):
        """ Registrations have a 24-hour timeout"""

        is_guest = user.is_guest

        password = kwargs.pop('password', None)
        first_name = kwargs.pop('first_name', None)
        last_name = kwargs.pop('last_name', None)
        phone = kwargs.pop('phone', None)
        expiry_timestamp = kwargs.pop('expiry_timestamp', timezone.now() + datetime.timedelta(minutes=cls.registration_lifetime))

        with transaction.atomic():
            user.is_verified = False
            user.save()

            inst = cls(email=user.email,
                       expiry_timestamp=expiry_timestamp)
            inst.save(*args, **kwargs)

            # Todo - should we defer setting data in all cases ???

            # For guest users we defer setting passwords, name and phone until the registration completes
            if is_guest:
                additional = AdditionalData(verifier=inst, password=password, first_name=first_name, last_name=last_name,
                                            phone=phone)
                additional.save(*args, **kwargs)

        return inst

class AdditionalData(models.Model):
    verifier = models.OneToOneField(RegistrationVerifier, on_delete=models.CASCADE, related_name='AdditionalData')
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    phone = models.CharField(max_length=13)
    password = models.CharField(max_length=128)


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

        expiry = kwargs.pop('expiry', timezone.now() + datetime.timedelta(minutes=cls.short_code_lifetime))
        retry_count = kwargs.pop('retry_count', cls.max_retry)

        inst = cls(email=email,
                   expiry_timestamp=expiry,
                   retry_count=retry_count,
                   reason_code=None)
        inst.save( *args, **kwargs)
        return inst


class PasswordResetApplication(UserVerification):

    password_reset_lifetime = 60

    class Meta:
        indexes = [
            models.Index(name='byUUID', fields=['uuid'])
        ]

    uuid = models.UUIDField(db_index=True)

    @classmethod
    def add_password_reset(cls, user, *args, **kwargs):
        """Password_resets have a 1-hour timeout"""

        with transaction.atomic():
            user.is_verified = False
            user.save()

            inst = cls(email=user.email,
                       expiry_timestamp=timezone.now() + datetime.timedelta(minutes=cls.password_reset_lifetime),
                       uuid=uuid1())
            inst.save(*args, **kwargs)

        return inst