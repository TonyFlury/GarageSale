
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
                'sub_category',
                'summary',
                'subject',
                'html_content',
                'signature',
                'use_from',]
        labels = {
            'category': 'Category',
            'sub_category': 'Sub-category',
            'html_content': 'Content',
            'subject': 'Subject',
        }
        widgets = {
            'html_content': SummernoteWidget(attrs={'summernote': {'width': '100%', 'height': '300px'}}),
            'sub_category': ComboBoxWidget([('1','One'),('2','Two')]),
            'signature': Textarea(attrs={'rows': 3}),
        }

class AttachmentForm(forms.ModelForm):
    class Meta:
        model = TemplateAttachment
        fields = ['upload', 'template_name', 'attached_file']


class CommunicationTemplateWebsiteForm(TemplateForm):
    """Reuse the template editor without category-specific sub_category choices."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["sub_category"].widget = forms.TextInput()
        self.fields["subject"].widget.attrs.update(size=80, style="max-width: 100%; box-sizing: border-box;")
        self.fields["use_from"].widget = forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"})
        # Editing a template keeps its category, including when POST data is tampered with.
        if self.instance.pk:
            self.fields["category"].widget = forms.HiddenInput()
            self.fields["category"].disabled = True


class CommunicationTemplateAttachmentForm(AttachmentForm):
    template_name = forms.CharField(max_length=100, required=False,
                                   help_text="Template summary in the same category and sub-category as this template.")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["upload"].widget.attrs["data-attachment-upload"] = ""
        # Ignore inactive inputs on the server as well as hiding them in the browser.
        upload = self.fields["upload"].widget.value_from_datadict(
            self.data, self.files, self.add_prefix("upload"),
        ) if self.is_bound else self.initial.get("upload", False)
        self.fields["template_name"].disabled = bool(upload)
        self.fields["attached_file"].disabled = not upload
        # Inactive file inputs must not validate or access an old stored file.
        if not upload:
            self.initial["attached_file"] = None

    def clean(self):
        cleaned = super().clean()
        # Uploaded attachments need a file; named attachments need a template name.
        if cleaned.get("upload"):
            if not cleaned.get("attached_file"):
                self.add_error("attached_file", "Choose a file for this attachment.")
            cleaned["template_name"] = ""
        else:
            if not cleaned.get("template_name"):
                self.add_error("template_name", "Enter the attachment template name.")
            # FileField treats None as "unchanged"; an empty string clears the file reference.
            cleaned["attached_file"] = ""
        return cleaned
