from django.db import models
from GarageSale.models import EventData

# Create your models here.


class Sponsor(models.Model):
    event = models.ForeignKey( EventData, related_name='sponsors', on_delete=models.CASCADE, null=True)
    company_name = models.CharField(max_length=120)
    logo = models.ImageField()
    description = models.TextField(max_length=1000)
    website = models.URLField(blank=True)
    facebook = models.URLField(blank=True)
    twitter = models.URLField(blank=True)
    instagram = models.URLField(blank=True)
    email = models.EmailField()
    phone = models.CharField(max_length=12)
    creation_date = models.DateTimeField(auto_now_add=True)
