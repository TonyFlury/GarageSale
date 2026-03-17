#--------------------------------------------------------------
#     library.py
#     10 March 2026
#
# Simple library to allow registration of entry points on the main team page
#--------------------------------------------------------------
from collections import namedtuple
from functools import wraps

from django.urls import reverse, reverse_lazy

EntryPoint = namedtuple('EntryPoint', 'url_path icon_path permission needs_event nav_page')
entry_points: dict[str, EntryPoint] = {}

class EntryPointMixin:
    entry_point_url = None
    entry_point_label = None
    entry_point_icon = None
    entry_point_permission = None
    entry_point_needs_event = True
    entry_point_nav_page = 'TeamPage'

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__( **kwargs)
        entry_points[cls.entry_point_label] = EntryPoint(cls.entry_point_url, cls.entry_point_icon, cls.entry_point_permission, cls.entry_point_needs_event, cls.entry_point_nav_page)

def register( label, url_path, icon_path, permission, needs_event=True, nav_page='TeamPage'):
        entry_points[label] = EntryPoint(url_path, icon_path, permission, needs_event, nav_page)

def get_entry_points( user=None, nav_page='TeamPage'):
    for key, value in sorted(entry_points.items()):
        if nav_page != value.nav_page:
            continue
        if not value.permission or (user and user.has_perm(value.permission)):
            yield {'name':key} |  value._asdict()