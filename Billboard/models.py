from django.db import models

from GarageSale.models import EventData
# Create your models here.


class BillboardLocations(models.Model):
    event = models.ForeignKey( EventData, related_name='billboards', on_delete=models.CASCADE, null=True)
    name = models.CharField(max_length=200)
    house_number = models.CharField(max_length=80)
    street_name = models.CharField(max_length=200)
    town = models.CharField(max_length=100, default='Brantham')
    postcode = models.CharField(max_length=10)
    phone = models.CharField(max_length=12)
    mobile = models.CharField(max_length=12)
    email = models.EmailField()
    installed = models.BooleanField(default=False)

