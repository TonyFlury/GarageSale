"""Register host navigation and optional providers without database operations."""
from django.apps import apps
from django.templatetags.static import static

from TeamPageFramework.entry_point import register


def configure_notifier():
    """Expose the review page and register Diary only when both applications are installed."""
    from Notifier.configuration import access_permissions
    register('Notifications', 'Notifier:feed', static('GarageSale/images/icons/email-open-svgrepo-com.svg'),
             access_permissions(), needs_event=False, nav_page='Overview', order=20)

    # The generic Notifier must remain usable when Diary is absent from an installation.
    if apps.is_installed('Diary'):
        from .diary_notifier import register as register_diary
        register_diary()
