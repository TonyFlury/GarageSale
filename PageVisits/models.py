from django.db import models

# Create your models here.

from django.db import models


class PageVisit(models.Model):
    path = models.CharField(max_length=500)
    sourceIP = models.GenericIPAddressField()
    timestamp = models.DateTimeField()
    method = models.CharField(default='GET', max_length=4)
    username = models.CharField(max_length=256)
    user_agent = models.CharField(max_length=500)
    response_code = models.IntegerField()
    referer = models.URLField()

    def __str__(self):
        return f"[{self.timestamp}] : '{self.user_agent}' {self.sourceIP} '{self.referer}' \'{self.username if self.username else 'Anonymous'}\' {self.method} '{self.path}' {self.response_code}"