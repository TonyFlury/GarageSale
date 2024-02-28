#!/usr/bin/env python
# coding=utf-8
"""
    GarageSale.pageVisits.py : 

Summary :
    
    
Use Case :
    
    
Testable Statements :
    ...
"""
from django.db.models import Model
from django.http import HttpResponse, HttpRequest
from django.conf import settings
from ..models import PageVisit

from threading import Timer
import threading
from datetime import datetime, timezone
from collections import deque
from dataclasses import dataclass, asdict


class CachedDeque(deque):
    """a special cache with maximum size and a maximum time between writes"""

    def __init__(self, model: Model, max_length=20, timeout=30):
        self.model: Model = model
        self.max_length: int = max_length
        self.timeout: float = timeout
        self.last_save: float = datetime.now().timestamp()
        super().__init__(maxlen=max_length + 1)
        self.timer: Timer = None

    def __write_out(self):
        self.model.objects.bulk_create(d)
        super().clear()
        self.last_save = datetime.now().timestamp()
        if self.timer:
            self.timer.cancel()
            self.timer = None

    def append(self, __x):
        entry: PageVisit
        if len(self) == self.max_length:
            self.__write_out()

        super().append(__x)
        if not self.timer:
            self.timer = threading.Timer(self.timeout, self.__write_out)
            self.timer.daemon = True
            self.timer.start()


class PageVisitRecorder:
    def __init__(self, get_response):
        """Initialise the middleware, including building the cache based on the settings"""
        self.get_response = get_response

    def __call__(self, request: HttpRequest):
        """Invoked on every request - capture the details and move on"""

        response: HttpResponse = self.get_response(request)

        inst = PageVisit(path=request.path,
                         timestamp=datetime.now(timezone.utc),
                         sourceIP=request.META['REMOTE_ADDR'],
                         method=request.method,
                         username=request.user.username,
                         user_agent=request.headers.get("User-Agent", ''),
                         referer=request.META.get('HTTP_REFERER', ''),
                         response_code=response.status_code)
        inst.save()

        return response
