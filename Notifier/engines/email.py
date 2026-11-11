"""Expose optional email queue intake without sending mail during notification collection."""
from Notifier.email.configuration import email_configuration


class EmailEngine:
    """Collate notification identities and defer all SMTP operations to the email worker command."""

    key = 'email'

    def __init__(self):
        """Validate host settings without database access or background process creation."""
        email_configuration()

    def notification_created(self, notification_id, recipient_id):
        """Retain one accepted notification when the recipient has explicitly enabled email."""
        from Notifier.models import EmailPreference, EmailQueueItem
        preference = EmailPreference.objects.filter(user_id=recipient_id, enabled=True).first()

        # Email is disabled by default and must never create settings as a side effect of intake.
        if preference is not None:
            from Notifier.models import EmailChannelPreference, Notification
            stream_key = Notification.objects.values_list('stream_key', flat=True).get(pk=notification_id)

            # Email channel selection must not alter collection or the icon engine's unread counts.
            if EmailChannelPreference.objects.filter(user_id=recipient_id, stream_key=stream_key, enabled=True).exists():
                EmailQueueItem.objects.get_or_create(notification_id=notification_id, defaults={'preference': preference})
