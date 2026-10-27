#--------------------------------------------------------------
#     library.py
#     10 March 2026
#
# Simple library to allow registration of entry points on the main team page
#--------------------------------------------------------------
from collections import namedtuple


EntryPoint = namedtuple('EntryPoint', 'url_path icon_path permission needs_event nav_page order', defaults=(100,))
entry_points: dict[str, EntryPoint] = {}

class EntryPointMixin:
    entry_point_url = None
    entry_point_label = None
    entry_point_icon = None
    entry_point_permission = None
    entry_point_needs_event = True
    entry_point_nav_page = 'TeamPage'
    entry_point_order = 100

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__( **kwargs)
        entry_points[cls.entry_point_label] = EntryPoint(
            cls.entry_point_url, cls.entry_point_icon, cls.entry_point_permission,
            cls.entry_point_needs_event, cls.entry_point_nav_page, cls.entry_point_order)

def register(label, url_path, icon_path, permission, needs_event=True, nav_page='TeamPage', order=100):
    """Register a function entry; lower order values appear first within its group."""
    entry_points[label] = EntryPoint(url_path, icon_path, permission, needs_event, nav_page, order)

def get_entry_points( user=None, nav_page='TeamPage'):
    """Filter a group by access, ordering by priority and then alphabetically.

    Default priority 100 preserves alphabetical ordering for existing callers,
    including account submenus. Five-argument EntryPoint construction still works.
    """
    # Duplicate priorities are valid; compare labels without case-sensitive surprises.
    ordered = sorted(entry_points.items(), key=lambda item: (item[1].order, (item[0] or '').casefold()))
    for key, value in ordered:
        # Grouping remains entirely controlled by each feature's registration.
        if nav_page != value.nav_page:
            continue
        # A tuple allows either the current capability or its legacy equivalent.
        permissions = value.permission if isinstance(value.permission, tuple) else (value.permission,)
        if not value.permission or (user and any(user.has_perm(permission) for permission in permissions)):
            yield {'name':key} |  value._asdict()
