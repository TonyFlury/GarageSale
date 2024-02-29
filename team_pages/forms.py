import datetime

from django import forms

from GarageSale.models import EventData, MOTD
from Sponsors.models import Sponsor
from News.models import NewsArticle


class EventForm(forms.ModelForm):
    class Meta:
        model = EventData
        fields = '__all__'


class SponsorForm(forms.ModelForm):
    class Meta:
        model = Sponsor
        exclude =['event']


class MotdForm(forms.ModelForm):
    class Meta:
        model = MOTD
        fields = '__all__'


class NewsForm(forms.ModelForm):
    class Meta:
        model = NewsArticle
        fields = '__all__'
        widgets = {'publish_by': forms.DateInput(attrs={'type': 'date'}),
                   'expire_by': forms.DateInput(attrs={'type': 'date'}),
                   'synopsis': forms.Textarea(attrs={'cols':45,'rows':4})}
        exclude = ['slug', 'published']

    def clean(self):
        cleaned_data = super().clean()

        if cleaned_data['front_page'] and not cleaned_data['synopsis']:
            self.add_error('synopsis', 'A synopsis must be provided for articles intended for the front-page')

