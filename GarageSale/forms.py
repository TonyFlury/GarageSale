
from django import forms
from django.contrib.auth import models
from django.forms import MultiWidget, Textarea
from django_summernote.widgets import SummernoteWidget, SummernoteInplaceWidget

from DjangoGoogleMap.forms import GoogleMap
from GarageSale.models import CommunicationTemplate, TemplateAttachment


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
