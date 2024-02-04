#!/usr/bin/env python
# coding=utf-8
"""
Simple middleware handler to insert the 'current_event' value into the request
"""

from ..models import EventData
from django.core import exceptions


class CurrentEvent:
    def __init__(self, get_response):
        self.get_response = get_response
        # One-time configuration and initialization.

    def __call__(self, request):
        """Add in current event data"""

        try:
            self._event = EventData.get_current()
        except exceptions.ObjectDoesNotExist:
            self._event = None

        request.current_event = self._event
        response = self.get_response(request)

        # Code to be executed for each request/response after
        # the view is called.

        return response