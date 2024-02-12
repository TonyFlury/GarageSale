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
import googlemaps

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


class EventData(models.Model):
    """Various Event settings - critical data
       There should be only be one instance here - the intention is to allow the web site to be reused across
       multiples years
    """
    objects = models.Manager()
    event_logo = models.ImageField()                # The specific logo for this years event
    event_date = models.DateField()                 # The date of the actual sale event
    open_billboard_bookings = models.DateField()    # When Billboard bookings open
    close_billboard_bookings = models.DateField()   # When Billboard bookings close
    open_sales_bookings = models.DateField()        # When Sales bookings open
    close_sales_bookings = models.DateField()       # When Sales bookings open
    use_from = models.DateField()

    @staticmethod
    def get_current():
        try:
            return (EventData.objects.filter(use_from__lte = datetime.date.today() )
                    .values_list(named=True).latest('use_from') )
        except EventData.DoesNotExist:
            return None


class Location(models.Model):
    user = models.ForeignKey(User, related_name='locations', on_delete=models.CASCADE, blank=True)
    house_number = models.CharField(max_length=80)
    street_name = models.CharField(max_length=200)
    town = models.CharField(max_length=100, default='Brantham')
    postcode = models.CharField(max_length=10)
    phone = models.CharField(max_length=12)
    mobile = models.CharField(max_length=12)

