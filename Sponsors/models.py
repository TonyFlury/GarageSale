from django.db import models
from GarageSale.models import EventData

# Create your models here.


class Sponsor(models.Model):
    event = models.ForeignKey( EventData, related_name='sponsors', on_delete=models.CASCADE, null=True)
    company_name = models.CharField(max_length=120)
    logo = models.ImageField()
    description = models.TextField(max_length=256)
    website = models.URLField()
    facebook = models.URLField()
    twitter = models.CharField(max_length=80)
    instagram = models.CharField(max_length=80)
    email = models.EmailField()
    phone = models.CharField(max_length=12)
    creation_date = models.DateTimeField(auto_now_add=True)
