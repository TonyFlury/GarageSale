"""
   Database credentials - DO NOT COMMIT to git

    This version is for the live Brantham Garage Sale Server - i.e remote postgreql server

    Use copy and paste to server only
"""
from pathlib import Path


def db_credentials( base_dir:Path) -> dict:
    return {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': 'garagesale2.0',
            'USER': 'garagesaleweb',
            'PASSWORD': '7RWrbJ18tZ',
            'HOST': 'BranthamGarageSale-235.postgres.eu.pythonanywhere-services.com',
            'PORT': '10235',
            },
        }
