"""Upload-path compatibility for historical Craft Market migrations.

Active trader data lives in Contributors.models. Historical migrations reconstruct
the old models themselves, but still reference this upload callable by import path.
"""
from django.utils.text import slugify


def save_logo_to(instance, file_name: str) -> str:
    return f'marketeer_{instance.event.event_date.year}/{slugify(instance.trading_name)}_{file_name}'
