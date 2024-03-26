from django.db import models
from django.contrib.auth.models import User
from django.core import exceptions

from GarageSale.models import EventData, Location
# Create your models here.


class BillboardLocations(models.Model):
    event = models.ForeignKey( EventData, related_name='billboards', on_delete=models.CASCADE, null=True)
    location = models.ForeignKey( Location, related_name='billboards', on_delete=models.CASCADE, null=True)
    installed = models.BooleanField(default=False)
    creation_date = models.DateField(auto_now_add=True)

    @staticmethod
    def has_applied(current_event_id, current_user):
        """Return the users instance of any application or None"""
        try:
            inst = BillboardLocations.objects.filter(event__id = current_event_id, location__user=current_user).get()
            return inst
        except exceptions.ObjectDoesNotExist:
            return None

    def name(self):
        return f'{self.location.user.first_name + " " + self.location.user.last_name}'

    def full_address(self):
        return f'{self.location.house_number + " " + self.location.street_name}'

    def csv(self):
        return (f'{self.location.user.first_name + " " + self.location.user.last_name},'
                f'{self.location.house_number + " " + self.location.street_name},'
                f'{self.location.postcode},'
                f'{self.location.phone},'
                f'{self.location.mobile}')