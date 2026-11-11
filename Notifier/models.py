"""Store personal preferences and collected entries independently of providers."""
from uuid import uuid4

from django.conf import settings
from django.db import models


def default_email_weekday():
    """Read the configured default digest weekday without creating personal settings."""
    from .email.configuration import email_configuration
    return email_configuration()['DEFAULT_WEEKDAY']


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


class EmailChannelPreference(models.Model):
    """Store personal email channel selections independently of notification collection and icon counts."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    stream_key = models.CharField(max_length=150)
    enabled = models.BooleanField(default=False)

    class Meta:
        """Keep one email choice for each personal channel without additional permissions."""

        default_permissions = ()
        constraints = [models.UniqueConstraint(fields=('user', 'stream_key'), name='notifier_email_channel_identity')]


class EmailPreference(models.Model):
    """Store one optional email policy and its next scheduled delivery for an account."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    enabled = models.BooleanField(default=False)
    frequency = models.CharField(max_length=9, default='daily', choices=(
        ('immediate', 'Immediate'), ('daily', 'Daily'), ('weekly', 'Weekly')))
    weekly_day = models.PositiveSmallIntegerField(default=default_email_weekday)
    revision = models.PositiveIntegerField(default=0)
    next_due_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        """Use existing personal notification permission for email preferences."""

        default_permissions = ()
        constraints = [models.CheckConstraint(check=models.Q(weekly_day__gte=0, weekly_day__lte=6),
                                               name='notifier_email_weekday')]


class EmailQueueItem(models.Model):
    """Retain notification identities for collation until Notifier validation removes them."""

    preference = models.ForeignKey(EmailPreference, on_delete=models.CASCADE, related_name='items')
    notification = models.OneToOneField(Notification, on_delete=models.CASCADE)

    class Meta:
        """Keep engine queue storage outside user-facing model administration."""

        default_permissions = ()


class EmailNotificationState(models.Model):
    """Retain attempt and successful-send history independently of the active email queue."""

    notification = models.OneToOneField(Notification, on_delete=models.CASCADE)
    last_attempted_at = models.DateTimeField(null=True, blank=True)
    last_sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        """Preserve reminder history when queue entries become invalid."""

        default_permissions = ()


class EmailDelivery(models.Model):
    """Record one durable delivery request and its single non-retried attempt."""

    preference = models.ForeignKey(EmailPreference, on_delete=models.CASCADE, related_name='deliveries')
    revision = models.PositiveIntegerField()
    key = models.CharField(max_length=200, unique=True)
    kind = models.CharField(max_length=12, choices=(('initial', 'Initial catch-up'), ('transition', 'Immediate catch-up'),
        ('immediate', 'Immediate'), ('scheduled', 'Scheduled digest'), ('manual', 'Manual digest')))
    status = models.CharField(max_length=10, default='pending', choices=(('pending', 'Pending'), ('attempting', 'Attempting'),
        ('sent', 'Sent'), ('empty', 'Empty'), ('skipped', 'Skipped'), ('failed', 'Failed')))
    due_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    notification_ids = models.JSONField(default=list)
    total = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True)

    class Meta:
        """Prevent duplicate scheduled claims and index pending engine work."""

        default_permissions = ()
        indexes = [models.Index(fields=('status', 'due_at'), name='notifier_email_due')]
