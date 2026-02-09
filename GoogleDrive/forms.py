from django import forms


class UploadToDriveForm(forms.Form):
    file = forms.FileField(label="Select a file")