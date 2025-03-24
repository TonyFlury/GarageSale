from django.contrib import admin
from .models import Location

@admin.register(Location)
class LocationAdminForm( admin.ModelAdmin):
    class Meta:
        model = Location
        fields = '__all__'
        list_filter = ['event']