from django.apps import AppConfig
from django.conf import settings


def appsettings():
    try:
        return settings.APPS_SETTINGS
    except AttributeError:
        return {}


class user_managementConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'user_management'
