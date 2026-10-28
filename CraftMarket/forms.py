"""Forms shared by the current and legacy RSVP portals."""
from django import forms
from django.utils import timezone
from decimal import Decimal


class RSVPForm(forms.Form):
        email = forms.EmailField(required=True)


class PitchPaymentForm(forms.Form):
    amount = forms.DecimalField(label='Pitch fee paid (£)', max_digits=12,
                                decimal_places=2, min_value=Decimal('0.01'))
    paid_on = forms.DateField(label='Payment date', initial=timezone.localdate,
                              widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'))
    reference = forms.CharField(label='Payment reference or note', max_length=254, required=False)

    def clean_paid_on(self):
        day = self.cleaned_data['paid_on']
        if day > timezone.localdate():
            raise forms.ValidationError('The payment date cannot be in the future.')
        return day


class BookingCancellationForm(forms.Form):
    reason = forms.CharField(label='Reason for cancellation', max_length=1000,
                             widget=forms.Textarea(attrs={'rows': 4}), initial='Pitch fee not received.')
    send_email = forms.BooleanField(label='Send cancellation email', required=False)
    email_template_id = forms.ChoiceField(label='Cancellation template', required=False)

    def __init__(self, *args, templates=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email_template_id'].choices = [(str(template.pk), template.summary or template.subject)
                                                    for template in templates]
        self.fields['send_email'].initial = bool(templates)
        if templates:
            self.fields['email_template_id'].initial = str(templates[0].pk)

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get('send_email'):
            # An expired template must not block an explicitly email-free cancellation.
            self._errors.pop('email_template_id', None)
            cleaned['email_template_id'] = ''
        if cleaned.get('send_email') and not cleaned.get('email_template_id'):
            self.add_error('email_template_id', 'Choose an available cancellation template, or turn off email.')
        return cleaned
