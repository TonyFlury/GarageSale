"""Initialize the generic Notifier without database reads or writes."""
from django.apps import AppConfig


class NotifierConfig(AppConfig):
    """Declare Notifier models and initialize optional configured engines."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'Notifier'

    def ready(self):
        """Validate host configuration without clearing providers registered by other applications."""
        from .configuration import configuration
        from .engines import validate_engines
        configuration()
        validate_engines()
