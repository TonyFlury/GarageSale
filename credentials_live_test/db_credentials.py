"""
   Database credentials - DO NOT COMMIT to git

    This version is for sqlite based non-secure test account.

    Use copy and paste to server only
"""
# Use BASE_DIR as defined in settings.py

from pathlib import Path


def db_credentials( base_dir:Path) -> dict:
    return {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': 'garagesale_test',
            'USER': 'garagesaleweb',
            'PASSWORD': '7RWrbJ18tZ',
            'HOST': 'BranthamGarageSale-235.postgres.eu.pythonanywhere-services.com',
            'PORT': '10235',
            },
        }

