from django.contrib import admin

# Register your models here.
from django.contrib import admin
from django import forms

from .models import Contributor, ContributorEvent, ContributorHistory, Contributions


@admin.register(Contributor)
class ContributorForm(admin.ModelAdmin):
    class Meta:
        model = Contributor
        fields = '__all__'

@admin.register(ContributorEvent)
class ContributorEventAdmin(admin.ModelAdmin):
    class Meta:
        model = ContributorEvent
        fields = '__all__'

@admin.register(ContributorHistory)
class ContributorHistoryAdmin(admin.ModelAdmin):
    class Meta:
        model = ContributorHistory
        fields = '__all__'

@admin.register(Contributions)
class ContributionsAdmin(admin.ModelAdmin):
    class Meta:
        model = Contributions
        fields = '__all__'
