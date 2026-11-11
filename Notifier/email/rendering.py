"""Build equivalent HTML and plain-text digests from revalidated notification summaries."""
from datetime import date
from urllib.parse import urljoin

from django.template.loader import render_to_string
from django.urls import reverse

from Notifier.registry import get_registry


def item_context(record, reminders, config):
    """Expose only the title, channel, date, destination, and reminder marker to email templates."""
    due = None
    try:
        due = date.fromisoformat(record.data.get('due_date', ''))
    except (ValueError, TypeError):
        pass
    registry = get_registry()
    reference = registry.streams[record.stream_key]
    provider = registry.providers[reference.provider_key].definition.label
    destination = record.action_url or reverse('Notifier:feed')
    return {'title': record.title, 'severity': record.severity, 'severity_label': record.get_severity_display(),
        'channel_key': record.stream_key, 'channel': f'{provider}: {record.stream_label}', 'date': due,
        'reminder': record.pk in reminders, 'url': urljoin(config['BASE_URL'], destination)}


def digest_context(delivery, records, total, reminders, now, config):
    """Prepare the ordered digest context without accessing task models or copying notification body text."""
    items = [item_context(record, reminders, config) for record in records]
    return {'items': items, 'total': total, 'shown': len(items), 'more': total - len(items), 'kind': delivery.kind,
        'date': now.astimezone(config['TIME_ZONE']).date(),
        'review_url': urljoin(config['BASE_URL'], reverse('Notifier:feed') + '?state=unread')}


def render_digest(context):
    """Return equivalent plain-text and HTML bodies using separate escaped presentation templates."""
    return (render_to_string('Notifier/email/digest.txt', context),
            render_to_string('Notifier/email/digest.html', context))
