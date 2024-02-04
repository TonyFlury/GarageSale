from django.contrib import admin

# Register your models here.

from django.contrib import admin
from .models import UserVerification

admin.site.register(UserVerification)