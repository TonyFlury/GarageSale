from django.db import models
from GarageSale.models import EventData
# Create your models here.

from django.conf import settings


class MultipleChoiceField(models.CharField):
    def __init__(self,*args, **kwargs):
        super().__init__(*args, **kwargs)

    def from_db_value(self, value, expression, connection):
        if value is None:
            return []

        return [i for i in value.split(',')]

    def to_python(self, value):
        if isinstance(value,set):
            return value

        if value is None:
            return []

        return [i for i in value.split(',') ]

    def get_prep_value(self, value):
        return ','.join(i for i in value)


# TODO - sanitise house_number (remove trailing spaces and punctuation).
# TODO - sanitise postcode - format to Incode/Outcode - CO[0-9]{2} [0-9][A-Z]{2}
# ToDO - How to spot duplicates ?

class Location(models.Model):
    objects = models.Manager()

    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='UserLocations', on_delete=models.CASCADE)
    event = models.ForeignKey(EventData,related_name='EventLocations', on_delete=models.CASCADE)
    ad_board = models.BooleanField(help_text="Do you want an advertising board at this location ?")
    sale_event = models.BooleanField(help_text="Do you plan to have a sale or another event at this location ?")
    house_number = models.CharField(max_length=80)
    street_name = models.CharField(max_length=200)
    postcode = models.CharField(max_length=10)
    town = models.CharField(max_length=100, default='Brantham')
    creation_timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return (f'{self.user.first_name + " " + self.user.last_name}  \n'
                f'{self.house_number}, {self.street_name}. {self.postcode}\n'
                f'Ad Board Here {"Yes" if "AdBoard" in self.category else "No"}\n'
                f'Sale Here {"Yes" if "Sale" in self.category else "No"}')

    def location_type(self):
        return (f"Sale {'&#x2705;' if self.sale_event else '&#x274E;'}  "
                f"Ad-Board {'&#x2705;' if self.ad_board else '&#x274E;'}")
