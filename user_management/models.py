from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User
from django.conf import settings


class UserVerification(models.Model):
    class Meta:
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['uuid']),
        ]
    email = models.EmailField(blank=False)
    creation_timestamp = models.DateTimeField(default=timezone.now)
    uuid = models.UUIDField()


class PasswordResetApplication(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='password_resets', on_delete=models.CASCADE)
    uuid = models.UUIDField( db_index=True)
