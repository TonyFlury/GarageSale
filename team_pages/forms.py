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

