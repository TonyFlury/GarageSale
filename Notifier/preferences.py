"""Validate declared fields and apply current personal preferences."""
from django import forms
from django.core.exceptions import ImproperlyConfigured, PermissionDenied, ValidationError
from django.db import transaction

from .definitions import FieldDefinition, StreamDefinition
from .registry import validate_key


FIELD_TYPES = {'boolean', 'integer', 'text', 'choice'}


def form_field(definition):
    """Construct a plain Django field without loading application records."""
    options = {'label': definition.label, 'required': definition.required, 'initial': definition.default,
               'help_text': definition.help_text}

    # Boolean preferences must accept an unchecked control as a valid false value.
    if definition.type == 'boolean':
        return forms.BooleanField(**{**options, 'required': False})

    # Integer limits apply to notice periods and other bounded application settings.
    if definition.type == 'integer':
        return forms.IntegerField(**options, min_value=definition.minimum, max_value=definition.maximum)

    # Stable choice values keep saved settings independent of display text.
    if definition.type == 'choice':
        return forms.ChoiceField(**options, choices=definition.choices)
    return forms.CharField(**options, max_length=1000)


def validate_definition(definition):
    """Reject unsupported field definitions and invalid defaults during memory registration."""

    # Stream declarations must have a stable identity and a supported settings schema.
    if not isinstance(definition, StreamDefinition):
        raise ImproperlyConfigured('Supply a StreamDefinition.')
    validate_key(definition.key)

    # Labels and positive versions keep stored settings and display snapshots meaningful.
    if (not isinstance(definition.label, str) or not definition.label.strip() or len(definition.label) > 200 or
            type(definition.schema_version) is not int or definition.schema_version < 1):
        raise ImproperlyConfigured('Supply a label and a positive schema version.')

    # A string group name must not become an iterable of individual characters.
    if definition.allowed_groups is not None and (
            not isinstance(definition.allowed_groups, tuple) or
            not all(isinstance(name, str) and name for name in definition.allowed_groups)):
        raise ImproperlyConfigured('Supply a tuple of group names or None.')
    for callback in (definition.recipient_resolver, definition.access_policy):

        # Invalid callbacks must fail during startup instead of silently suppressing notifications.
        if callback is not None and not callable(callback):
            raise ImproperlyConfigured('Stream resolvers and access policies must be callable.')
    keys = set()
    for item in definition.fields:

        # A declared field must support the same validation and form interface.
        if not isinstance(item, FieldDefinition):
            raise ImproperlyConfigured('Supply FieldDefinition values.')
        validate_key(item.key)

        # Duplicate or unsupported fields cannot produce a safe settings form.
        if item.key in keys or item.key == 'enabled' or item.type not in FIELD_TYPES:
            raise ImproperlyConfigured('Invalid or duplicate stream field: ' + item.key)
        keys.add(item.key)
        try:
            form_field(item).clean(item.default)
        except ValidationError as error:
            raise ImproperlyConfigured('Invalid default for ' + item.key) from error


def can_use(user):
    """Return whether the active authenticated user has Notifier access."""
    return bool(user.is_authenticated and user.is_active and user.has_perm('Notifier.use_notifier'))


def eligible_for_stream(user, definition):
    """Apply Notifier authorization and optional stream group restrictions."""

    # Saved preferences must never act as an authorization grant.
    if not can_use(user):
        return False

    # An omitted restriction permits authorized users. An empty restriction permits nobody.
    if definition.allowed_groups is None:
        return True
    return user.groups.filter(name__in=definition.allowed_groups).exists()


def clean_values(definition, values):
    """Validate a complete settings mapping and return normalized JSON values."""
    fields = {item.key: item for item in definition.fields}

    # Unknown values must not survive an incompatible settings schema change.
    if not isinstance(values, dict) or set(values) - fields.keys():
        raise ValidationError('Unknown stream settings.')
    return {key: form_field(item).clean(values.get(key, item.default)) for key, item in fields.items()}


def saved_subscription(user, key):
    """Read existing preferences without creating a default subscription."""
    from .models import Subscription
    return Subscription.objects.filter(user=user, stream_key=key).first()


def subscription_is_valid(subscription, definition):
    """Reject disabled or incompatible saved settings without modifying them."""

    # A missing, disabled, or old-schema preference must not enable notifications.
    if subscription is None or not subscription.enabled or subscription.schema_version != definition.schema_version:
        return False
    try:
        clean_values(definition, subscription.values)
    except ValidationError:
        return False
    return True


@transaction.atomic
def save_subscription(user, definition, *, enabled, values):
    """Authorize and validate a personal settings change before saving its subscription row."""
    from .models import Subscription

    # A forged stream selection must not create an unauthorized preference row.
    if not eligible_for_stream(user, definition):
        raise PermissionDenied('This stream is unavailable.')

    # Direct API callers must supply a boolean rather than a truthy string.
    if type(enabled) is not bool:
        raise ValidationError('Supply a boolean enabled setting.')
    normalized = clean_values(definition, values)
    row, _ = Subscription.objects.update_or_create(user=user, stream_key=definition.key,
        defaults={'enabled': enabled, 'values': normalized, 'schema_version': definition.schema_version})
    return row
