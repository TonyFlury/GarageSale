"""Forms shared by the current and legacy RSVP portals."""
from django import forms


class RSVPForm(forms.Form):
        email = forms.EmailField(required=True)
