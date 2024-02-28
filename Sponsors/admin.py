from django.contrib import admin

# Register your models here.
from django.contrib import admin
from django import forms

from .models import Sponsor


class SponsorForm(forms.ModelForm):
    class Meta:
        model=Sponsor
        fields = '__all__'


@admin.register(Sponsor)
class SponsorAdmin(admin.ModelAdmin):
    form = SponsorForm
    list_display = ['company_name']
    date_hierarchy = 'creation_date'
