from django import forms
from django.core.exceptions import ImproperlyConfigured

from .widgets import GoogleMapWidget
from django.conf import settings

#TODO Validate location is within boundary ????

class GoogleMap(forms.Field):
    """"Define a fields which displays an interactive Google map"""
    widget = GoogleMapWidget

    def __init__(self, *args, place=None, **kwargs):
        self._place = place # Needs to be set before __init__ is called on superclass
        if place and place not in settings.GOOGLE_MAP_SETTINGS.get('PLACES',{}):
            raise ValueError(f'Google Map place {place} must be in GOOGLE_MAP_SETTINGS')

        kwargs.pop('max_length', None)
        super().__init__(*args, **kwargs)

    def widget_attrs(self, widget):
        attrs = super().widget_attrs(widget)
        try:
            attrs['API_KEY'] = settings.GOOGLE_MAP_SETTINGS['API_KEY']
        except KeyError:
            raise ImproperlyConfigured("API_KEY must be in GOOGLE_MAP_SETTINGS")
        try:
            attrs['MAP_ID'] = settings.GOOGLE_MAP_SETTINGS['MAP_ID']
        except KeyError:
            raise ImproperlyConfigured("MAP_ID must be in GOOGLE_MAP_SETTINGS")

        if self._place:
            place_data = settings.GOOGLE_MAP_SETTINGS['PLACES'][self._place]
            place_fields = ['bounds', 'center', 'defaultZoom', 'autoZoomLevel', 'zoomStep', 'title']
            attrs |= {key: value for key, value in place_data.items() if key in place_fields}

        return attrs
