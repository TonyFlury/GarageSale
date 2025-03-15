#!/usr/bin/env python
# coding=utf-8
"""
    GarageSale.models.py : 

Summary :
    
    
Use Case :
    
    
Testable Statements :
    ...
"""
import datetime

from django.db import models
from django_quill.fields import QuillField
from django.contrib.auth.models import User

from django.contrib.auth.models import AbstractUser
from django.conf import settings

from GarageSale.svgaimagefield import SVGAndImageFormField


class General(models.Model):
    class Meta:
        managed = False
        default_permissions = ()
        permissions = [
            ("is_trustee", "Is a member of the Charity Trustee Team"),
           ("is_administrator", 'Is a administrator for the website'),
            ("is_manager", 'Is a manager of the website'),
        ]

class MOTD(models.Model):
    """"Holder for Message of the Day"""
    use_from = models.DateField()
    content = QuillField(default='')
    synopsis = models.CharField(max_length=256, null=True)

    @staticmethod
    def get_current():
        try:
            return MOTD.objects.filter(use_from__lte = datetime.date.today()).latest('use_from')
        except MOTD.DoesNotExist:
            return None

    class Meta:
        default_permissions = ()
        permissions = [
            ("can_create_motd", "Can create a new MotD"),
            ("can_edit_motd", "Can edit an existing MotD"),
            ("can_view_motd", "Can view an existing MotD"),
            ("can_delete_motd", "Can delete an existing MotD"),
        ]

def save_supported_logo_to(instance, filename):
    return f'supported_logo_{instance.name}/{filename}'

class byIndex(models.Manager):
    def get_queryset(self):
        return super(byIndex, self).get_queryset().order_by('index')

class Supporting(models.Model):
    objects = byIndex()
    name = models.CharField(max_length = 100)
    logo = models.FileField(upload_to=save_supported_logo_to, null=True, blank=True)
    website = models.URLField()
    index = models.IntegerField()
    def __str__(self):
        return self.name



class CurrentFuture(models.Manager):
    def get_queryset(self):
        return (super().get_queryset().filter(event_date__gte=datetime.date.today())
                                      .order_by('event_date'))


def save_event_logo_to(instance, filename):
    return f'event_logo_{instance.event_date.year}-{instance.event_date.month}/{filename}'


class EventData(models.Model):
    """Various Event settings - critical data
    """
    objects = models.Manager()
    CurrentFuture = CurrentFuture()
    event_logo = models.FileField(null=True, upload_to=save_event_logo_to)    # The specific logo for this years event
    event_date = models.DateField()                                             # The date of the actual sale event
    open_billboard_bookings = models.DateField(null=True)                                # When Billboard bookings open
    close_billboard_bookings = models.DateField(null=True)                               # When Billboard bookings close
    open_sales_bookings = models.DateField(null=True)                                    # When Sales bookings open
    close_sales_bookings = models.DateField(null=True)                                   # When Sales bookings open
    use_from = models.DateField()
    supporting_organisations = models.ManyToManyField(Supporting, related_name='by_event')

    def __str__(self):
        return f'{self.event_date}'

    class Meta:
        default_permissions = ()
        permissions = [
            ("can_create_event", "Can create a new Event"),
            ("can_edit_event", "Can edit an existing Event"),
            ("can_view_event", "Can view an existing Event"),
            ("can_delete_event", "Can delete an existing Event"),
            ("can_use_event", "Can use an existing Event")
        ]

    @staticmethod
    def get_current():
        try:
            e = (EventData.objects.filter(use_from__lte = datetime.date.today(),
                                             event_date__gte = datetime.date.today()).earliest('event_date') )
            return e
        except EventData.DoesNotExist:
            return None
