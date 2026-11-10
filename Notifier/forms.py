"""Render registered personal stream settings without provider-specific forms."""
from django import forms

from .preferences import form_field


class SubscriptionForm(forms.Form):
    """Present opt-in and the fields declared by one eligible registered stream."""

    enabled = forms.BooleanField(required=False, label='Enable this channel')

    def __init__(self, *args, definition, subscription=None, **kwargs):
        """Build fields from current declarations without creating a subscription row."""
        kwargs.setdefault('prefix', definition.key)
        super().__init__(*args, **kwargs)
        self.initial['enabled'] = False
        for field in definition.fields:
            self.fields[field.key] = form_field(field)
            self.initial[field.key] = field.default

        # Existing compatible settings can populate the form without acting as an access grant.
        if subscription is not None and subscription.schema_version == definition.schema_version:
            self.initial.update(subscription.values)
            self.initial['enabled'] = subscription.enabled

    def setting_values(self):
        """Return normalized application fields after successful form validation."""

        # Enablement belongs to the Notifier rather than the provider's settings mapping.
        return {key: value for key, value in self.cleaned_data.items() if key != 'enabled'}
