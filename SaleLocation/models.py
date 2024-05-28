from django.db import models
from django.contrib.auth.models import User
from GarageSale.models import EventData, Location

# Create your models here.

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


class SaleLocations(models.Model):
    location = models.ForeignKey( Location, related_name='Sales', on_delete=models.CASCADE, null=True)
    event = models.ForeignKey( EventData, related_name='Sales', on_delete=models.CASCADE, null=True)
    gift_aid = models.BooleanField('Sign up for GiftAid ?', default=False)
    minimum_paid = models.BooleanField(default=False)
    category = MultipleChoiceField(max_length=500, default=['Other'], null=True)
    creation_date = models.DateField(auto_now_add=True)

    def __str__(self):
        return str(self.location)

    def get_bacs_reference(self):
        return f'{self.event.event_date.year}-{self.location.postcode}-{self.location.house_number}'.replace(' ','')[0:15]

    def name(self):
        return f'{self.location.user.first_name + " " + self.location.user.last_name}'

    def full_address(self):
        return f'{self.location.house_number + " " + self.location.street_name}'