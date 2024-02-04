from django.db import models
from django.utils import timezone


class UserVerification(models.Model):
    class Meta:
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['uuid']),
        ]
    email = models.EmailField(blank=False)
    creation_timestamp = models.DateTimeField(default=timezone.now)
    uuid = models.UUIDField()

