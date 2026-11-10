"""Render registered personal stream settings without provider-specific forms."""
from django import forms

from .preferences import form_field


class ReviewFilterForm(forms.Form):
    """Validate optional review filters against current authorized channel choices."""

    severity = forms.ChoiceField(required=False, choices=(('', 'All severities'),
        ('urgent', 'Urgent'), ('warning', 'Warning'), ('information', 'Information')))
    channel = forms.ChoiceField(required=False, choices=())

    def __init__(self, *args, channels, **kwargs):
        """Supply authorized channels without exposing unavailable provider declarations."""
        super().__init__(*args, **kwargs)
        self.fields['channel'].choices = [('', 'All channels'), *channels]
        for field in self.fields.values():
            field.widget.attrs['class'] = 'notifier-filter-control'


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
        self.channel_enabled = self.initial['enabled']

        # Submitted enablement controls editing for this request rather than the previously saved state.
        if self.is_bound:
            self.channel_enabled = self.fields['enabled'].clean(self.data.get(self.add_prefix('enabled')))
        self.fields['enabled'].widget.attrs['class'] = 'notifier-channel-enabled'
        for field in definition.fields:

            # Disabled channels retain saved settings and ignore forged or omitted option values.
            if not self.channel_enabled:
                self.fields[field.key].disabled = True

    def setting_values(self):
        """Return normalized application fields after successful form validation."""

        # Enablement belongs to the Notifier rather than the provider's settings mapping.
        return {key: value for key, value in self.cleaned_data.items() if key != 'enabled'}
