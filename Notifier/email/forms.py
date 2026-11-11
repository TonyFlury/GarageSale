"""Display personal email policies without creating default database rows."""
from django import forms

from Notifier.models import EmailPreference
from .configuration import email_configuration


class EmailChannelForm(forms.Form):
    """Present a separate email selection without changing provider-defined settings."""

    enabled = forms.BooleanField(required=False, label='Include in email')

    def __init__(self, data=None, *, stream_key, enabled=False):
        """Bind one channel's email checkbox using a distinct prefix and saved initial value."""
        super().__init__(data=data, prefix=f'email-channel-{stream_key}', initial={'enabled': enabled})
        self.fields['enabled'].widget.attrs['class'] = 'notifier-channel-email-enabled styled-checkbox'


class EmailPreferenceForm(forms.Form):
    """Validate one opt-in policy and preserve disabled control values."""

    enabled = forms.BooleanField(required=False, label='Enable email notifications')
    frequency = forms.ChoiceField(choices=EmailPreference._meta.get_field('frequency').choices)
    weekly_day = forms.TypedChoiceField(coerce=int, choices=tuple(enumerate(
        ('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'))))

    def __init__(self, data=None, *, preference=None):
        """Use configured defaults until the user saves a policy. Disable inactive controls."""
        initial = {'enabled': False, 'frequency': 'daily', 'weekly_day': email_configuration()['DEFAULT_WEEKDAY']}

        # Existing personal choices take precedence over installation defaults.
        if preference is not None:
            initial = {key: getattr(preference, key) for key in initial}
        super().__init__(data=data, initial=initial, prefix='email')
        enabled = initial['enabled']
        frequency = initial['frequency']

        # Bound forms must use the submitted enable control before disabled fields are cleaned.
        if data is not None:
            enabled = self.fields['enabled'].clean(data.get('email-enabled'))
            frequency = data.get('email-frequency', frequency)
        self.fields['enabled'].widget.attrs['class'] = 'notifier-email-enabled styled-checkbox'
        self.fields['frequency'].widget.attrs['class'] = 'notifier-email-frequency'
        self.fields['weekly_day'].widget.attrs['class'] = 'notifier-email-weekday'
        self.fields['frequency'].disabled = not enabled
        self.fields['weekly_day'].disabled = not enabled or frequency != 'weekly'
