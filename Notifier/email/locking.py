"""Serialize email collation per account through PostgreSQL session advisory locks."""
from contextlib import contextmanager

from django.core.exceptions import ImproperlyConfigured
from django.db import connections


@contextmanager
def email_lock(user_id):
    """Yield one lock acquisition result and release the dedicated session after delivery."""
    connection = connections['default'].copy(alias='notifier_email_lock')

    # The project requires PostgreSQL for worker coordination in development, tests, and production.
    if connection.vendor != 'postgresql':
        raise ImproperlyConfigured('The email worker requires PostgreSQL.')
    try:
        connection.ensure_connection()
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_try_advisory_lock(hashtextextended(%s, 0))', [f'Notifier.email:{user_id}'])
            acquired = cursor.fetchone()[0]
        yield acquired
    finally:
        connection.close()
