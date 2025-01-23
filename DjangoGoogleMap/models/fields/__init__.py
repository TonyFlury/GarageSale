from django.db import models

from DjangoGoogleMap.forms import GoogleMap


class GoogleLocation(models.CharField):
    """"Define a database fields which displays a GoogleLocation (actually a json lng/lat pair) from a map"""

    description = "Record a Location from a GoogleMap entry - ie long and lat in string format"
    def __init__(self, *args, **kwargs):
        kwargs['max_length'] = 60
        super().__init__(*args, **kwargs)

    def get_internal_type(self):
        return "CharField"

    def value_to_string(self, obj):
        value = self.value_from_object(obj)
        return self.get_prep_value(value)

    def formfield(self, **kwargs):
        """Generate an instance of the GoogleMap fields automatically for this fields (used by ModelForm etc)."""
        return super().formfield(
            **{
                "form_class": GoogleMap,
                **kwargs,
            }
        )
