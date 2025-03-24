"""
    File : stats_view.py

    Statistics view functions

"""
from unicodedata import category

from django.template.response import TemplateResponse

from GarageSale.models import EventData
from datetime import date
from collections import namedtuple
from Location.models import Location

def event_stats(request, event_id=None):
    """"Provide stats for this given event - so far it is counts of Billboard and sales locations """

    def nice(inc):
        return ('+' if inc >= 0 else '') + str(inc)

    Stats_entry = namedtuple('Stats_entry', "name, total, increment")

    the_event = EventData.objects.get(id=event_id)
    all_entries = Location.objects.filter(event=the_event)

    category = {'AdBoards': 'ad_board',
                'Sale': 'sale_event'}

    stats = []

    for item, field in category.items():
        this_category = all_entries.filter(**{f'{field}':True})
        total = this_category.count()
        yesterday = this_category.filter( creation_timestamp__lt=date.today()).count()
        entry = Stats_entry(name=item,
                            total=total,
                            increment=nice(total - yesterday))
        stats.append(entry)

    return TemplateResponse(request, "event/stats/event_stats.html",
                            context={'event_id': the_event.id,
                                     'stats': stats})
