
from django import forms
from django.contrib.auth import models
from django.core.exceptions import ValidationError
from django.forms import MultiWidget, Textarea
from django_summernote.widgets import SummernoteWidget, SummernoteInplaceWidget

from DjangoGoogleMap.forms import GoogleMap
from GarageSale.models import CommunicationTemplate, TemplateAttachment, Nomination


class NominationCreate(forms.ModelForm):
    class Meta:
        model = Nomination
        fields = [
            'nominee',
            'contact_phone',
            'contact_email',
            'nominator',
            'nominator_email',
            'anonymous',
            'community_activities',
            'spending_plans',
        ]
        widgets = {
            'community_activities': Textarea(attrs={'rows': 4}),
            'spending_plans': Textarea(attrs={'rows': 4}),
        }

    def __init__(self, *args, **kwargs):
        self._user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if self._user and self._user.is_authenticated:
            self.fields['nominator'].initial = self._user.full_name()
            self.fields['nominator_email'].initial = self._user.email

    def clean(self):
        cleaned_data = super().clean()
        if self._user and self._user.is_authenticated:
            cleaned_data['nominator'] = self._user.full_name()
            cleaned_data['nominator_email'] = self._user.email
        elif not cleaned_data.get('nominator'):
            raise ValidationError({'nominator': 'Please provide your name'})
        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self._user and self._user.is_authenticated:
            instance.nominator = self._user.full_name()
            instance.nominator_email = self._user.email
        if commit:
            instance.save()
            self.save_m2m()
        return instance


class ComboBoxWidget(MultiWidget):
    def __init__(self, choices=None, attrs=None):
        if choices is None:
            raise ValueError('Choices must be provided')
        self.choices = choices
        widgets = {
            '': forms.Select(attrs=attrs, choices=choices + [('Other','Other')]),
            'other_entry':forms.TextInput(attrs=attrs),
        }
        super().__init__(widgets, attrs)


    def decompress(self, value):
        if value not in self.choices:
            return ['Other', value]
        else:
            return [value, '']

    def value_from_datadict(self, data, files, name):
        data = super().value_from_datadict(data, files, name)
        if data[0] == 'Other':
            return data[1]
        else:
            return data[0]

class TemplateForm(forms.ModelForm):
    class Meta:
        model = CommunicationTemplate
        fields = ['category',
                'transition',
                'summary',
                'subject',
                'html_content',
                'signature',
                'use_from',]
        labels = {
            'category': 'Category',
            'transition': 'Transition/Type',
            'html_content': 'Content',
            'subject': 'Subject',
        }
        widgets = {
            'html_content': SummernoteWidget(attrs={'summernote': {'width': '100%', 'height': '300px'}}),
            'transition': ComboBoxWidget([('1','One'),('2','Two')]),
            'signature': Textarea(attrs={'rows': 3}),
        }

class AttachmentForm(forms.ModelForm):
    class Meta:
        model = TemplateAttachment
        fields = ['upload', 'template_name', 'attached_file']
