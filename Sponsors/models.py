from django.db import models
from GarageSale.models import EventData

# Create your models here.

from django.utils.text import slugify


def save_logo_to( instance, file_name:str):
    return f'sponsors_{instance.event.event_date.year}/{slugify(instance.company_name)}_{file_name}'


class Sponsor(models.Model):
    event = models.ForeignKey( EventData, related_name='sponsors', on_delete=models.CASCADE, null=True)
    company_name = models.CharField(max_length=120)
    logo = models.ImageField( upload_to=save_logo_to, blank=True)
    description = models.TextField(max_length=1000)
    website = models.URLField(blank=True)
    facebook = models.URLField(blank=True)
    twitter = models.URLField(blank=True)
    instagram = models.URLField(blank=True)
    email = models.EmailField()
    phone = models.CharField(max_length=12)
    creation_date = models.DateTimeField(auto_now_add=True)
    confirmed = models.BooleanField(default=False)

    class Meta:
        default_permissions = ()
        permissions = [
            ("can_create_sponsor", "Can record a new Sponsor"),
            ("can_edit_sponsor", "Can edit an existing Sponsor"),
            ("can_view_sponsor", "Can view an existing Sponsor"),
            ("can_delete_sponsor", "Can delete an existing Sponsor"),
            ("can_confirm_sponsor", "Can confirm a Sponsor")
        ]