from django.core.exceptions import ImproperlyConfigured
from django.forms import Widget
from django.conf import settings

# ToDo - expand this to pass in things like API keys, boundaries etc

class GoogleMapWidget(Widget):
    template_name = "forms/widgets/GoogleMapWidget.html"

    def __init__(self, place=None, attrs=None):
        attrs = attrs or {}
        if place:
            if place not in settings.GOOGLE_MAP_SETTINGS['PLACES']:
                raise ImproperlyConfigured(f"{place} is not a valid Google Map place - check your settings")

            place_data = settings.GOOGLE_MAP_SETTINGS['PLACES'][place]
            place_fields = ['bounds', 'center', 'defaultZoom', 'autoZoomLevel', 'zoomStep', 'title']
            attrs |= {key: value for key, value in place_data.items() if key in place_fields}

        super().__init__(attrs)

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        widget_attrs = context.get('widget', {}).get('attrs', {})
        widget_attrs.setdefault('MapTypeId', 'roadmap')
        widget_attrs.setdefault('MAP_ID', 'DEMO_MAP_ID')

        # Default is victoria Monument, London
        widget_attrs.setdefault('center', '{"lat" : 51.50187794219808, "lng" : -0.14057285347341908}')
        widget_attrs.setdefault('defaultZoom', 8)
        widget_attrs.setdefault('autoZoomLevel', 19)
        widget_attrs.setdefault('zoomStep', 2)
        widget_attrs.setdefault('title', 'Your Location')

        return context