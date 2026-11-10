"""Coordinate workers and evaluation passes with PostgreSQL session advisory locks."""
from contextlib import contextmanager
from dataclasses import dataclass

from django.core.exceptions import ImproperlyConfigured
from django.db import connections


@dataclass
class Lease:
    """Retain one dedicated PostgreSQL session and the result of its lock attempt."""

    connection: object
    session: object
    acquired: bool

    def check(self):
        """Raise RuntimeError if the original lock session is no longer usable."""

        # Reconnecting cannot preserve session locks, so a lost connection must stop the worker.
        if self.connection.connection is not self.session or not self.connection.is_usable():
            raise RuntimeError('The Diary monitor lost its PostgreSQL lock session.')


@contextmanager
def monitor_lock(name):
    """Try one database-specific advisory lock and release it by closing the dedicated session."""
    connection = connections['default'].copy(alias='diary_monitor_lock')

    # Monitor coordination requires the project's approved PostgreSQL backend.
    if connection.vendor != 'postgresql':
        raise ImproperlyConfigured('The Diary monitor requires PostgreSQL.')
    try:
        connection.ensure_connection()
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_try_advisory_lock(hashtextextended(%s, 0))', ['GarageSale.diary_monitor.' + name])
            acquired = cursor.fetchone()[0]
        yield Lease(connection, connection.connection, acquired)
    finally:
        connection.close()
