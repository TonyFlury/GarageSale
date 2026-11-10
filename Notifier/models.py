"""Store personal preferences and collected entries independently of providers."""
from uuid import uuid4

from django.conf import settings
from django.db import models


class SeverityPreference(models.Model):
    """Store personal severity switches without creating rows for default settings."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    urgent = models.BooleanField(default=True)
    warning = models.BooleanField(default=False)
    information = models.BooleanField(default=False)

    class Meta:
        """Use personal Notifier access rather than separate administrative permissions."""

        default_permissions = ()


class Subscription(models.Model):
    """Persist settings only after a user changes a registered stream's preferences."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    stream_key = models.CharField(max_length=150)
    enabled = models.BooleanField(default=False)
    schema_version = models.PositiveIntegerField(default=1)
    values = models.JSONField(default=dict)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        """Keep one settings row for each user and stable stream key."""

        default_permissions = ()
        constraints = [models.UniqueConstraint(fields=('user', 'stream_key'), name='notifier_subscription_identity')]


class Notification(models.Model):
    """Retain one accepted occurrence for one recipient, with independent review state."""

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    stream_key = models.CharField(max_length=150)
    stream_label = models.CharField(max_length=200)
    occurrence_key = models.CharField(max_length=200)
    title = models.CharField(max_length=200)
    text = models.TextField()
    source = models.JSONField(default=dict)
    data = models.JSONField(default=dict)
    payload_version = models.PositiveIntegerField(default=1)
    content_hash = models.CharField(max_length=64)
    occurred_at = models.DateTimeField()
    sort_at = models.DateTimeField(null=True, blank=True)
    severity = models.CharField(max_length=11, default='information',
        choices=(('information', 'Information'), ('warning', 'Warning'), ('urgent', 'Urgent')))
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)
    action_label = models.CharField(max_length=80, blank=True)
    action_url = models.CharField(max_length=500, blank=True)

    @property
    def severity_icon(self):
        """Return a decorative symbol for the visible severity label."""
        return {'information': 'ⓘ', 'warning': '⚠', 'urgent': '!'}.get(self.severity, 'ⓘ')

    class Meta:
        """Enforce occurrence identity and index the personal review list."""

        default_permissions = ()
        permissions = [('use_notifier', 'Can review notifications and change personal stream settings')]
        ordering = ('-created_at', '-pk')
        constraints = [models.UniqueConstraint(fields=('user', 'stream_key', 'occurrence_key'),
                                               name='notifier_notification_identity')]
        indexes = [models.Index(fields=('user', '-created_at'), name='notifier_personal_feed')]
