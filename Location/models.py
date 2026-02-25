from datetime import datetime
from datetime import timezone
import string

from django.db import models

import DjangoGoogleMap.models.fields
from GarageSale.models import EventData
# Create your models here.

from django.conf import settings

from DjangoGoogleMap import models as GoogleMapModels

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
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='UserLocations', on_delete=models.CASCADE)
    event = models.ForeignKey(EventData,related_name='EventLocations', on_delete=models.CASCADE)
    ad_board = models.BooleanField(help_text="Do you want an advertising board at this location ?")
    sale_event = models.BooleanField(help_text="Do you plan to have a sale or another event at this location ?")
    house_number = models.CharField(max_length=80, null=False, blank=True, default='')
    street_name = models.CharField(max_length=200, null=False, blank=True,)
    postcode = models.CharField(max_length=10,  null=False, blank=True,)
    town = models.CharField(max_length=100, default='Brantham', null=False, blank=True,)
    lng_lat = DjangoGoogleMap.models.fields.GoogleLocation(verbose_name='Sale/AdBoard location')
    creation_timestamp = models.DateTimeField(auto_now_add=True)
    ad_board_timestamp = models.DateTimeField(null=True, blank=True, default=None)
    sale_timestamp = models.DateTimeField(null=True, blank=True, default=None)

    def save(self, *args, **kwargs):
        """Record the timestamps for the ad-board and sale events being set.
            Ensures the timestamps are set to None when the flags are cleared.
        """
        # Remove any trailing spaces and punctuation
        self.house_number = self.house_number.strip()
        self.house_number = self.house_number.replace(string.punctuation,'')

        # Set the timestamp for the ad-board and sale events
        if self.ad_board :
            if self.ad_board_timestamp is None:
                self.ad_board_timestamp = datetime.now(tz=timezone.utc)
        else:
            self.ad_board_timestamp = None

        if self.sale_event:
            if self.sale_timestamp is None:
                self.sale_timestamp = datetime.now(tz=timezone.utc)
        else:
            self.sale_timestamp = None
        super().save(*args, **kwargs)

    def full_address(self):
        return f'{self.house_number}, {self.street_name}, {self.town}.'

    def __str__(self):
        return (f'{self.user.email}\n'
                f'{self.house_number}, {self.street_name}. {self.postcode}\n'
                f'Ad Board Here {"Yes" if self.ad_board else "No"}\n'
                f'Sale Here {"Yes" if self.sale_event else "No"}')

    def location_type(self):
        return (f"Sale {'&#x2705;' if self.sale_event else '&#x274E;'}  "
                f"Ad-Board {'&#x2705;' if self.ad_board else '&#x274E;'}")

    def possible_duplicate(self):
        """Is this location already entered"""
        inst = Location.objects.filter(user=self.user, event=self.event, house_number=self.house_number, postcode=self.postcode).exclude(pk=self.pk)
        return True if inst.exists() else False

    def simple_hash(self, length=4):
        """This is not a cryptographic hash - this function simply serves to
        to generate an obfuscated 'value' for the row to prevent accidental access"""
        modulo = 2**(2**length)-1
        rawdata:bytes = (self.user.email + self.house_number + self.postcode).encode('utf-8')
        return f'{(sum(c for c in rawdata) % modulo):04X}'

    def ext_id(self):
        """Generate the full external id for this record"""
        return f'{self.id:04X}' + self.simple_hash()

    @classmethod
    def get_by_ext_id(cls, ext_id):
        inst = cls.objects.get(pk=int(ext_id[:4],base=16))
        return inst if inst and (inst.ext_id() == ext_id) else None
