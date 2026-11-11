"""Pass accepted notification identities to optional engines without coupling intake to a delivery implementation."""
import logging

from django.db import transaction

from .engines import configured_engine_paths, loaded_engines

logger = logging.getLogger(__name__)


def notify_engines(notification):
    """Enqueue a new recipient notification through optional engine callbacks inside isolated savepoints."""
    for engine in loaded_engines(configured_engine_paths()).values():
        callback = getattr(engine, 'notification_created', None)

        # Read-only engines do not require intake callbacks.
        if callback is None:
            continue
        try:
            with transaction.atomic():
                callback(notification.pk, notification.user_id)
        except Exception:
            logger.exception('Notifier engine intake failed: engine=%s notification=%s', engine.key, notification.pk)
