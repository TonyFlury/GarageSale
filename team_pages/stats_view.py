"""
    File : stats_view.py

    Statistics view functions

"""
from django.template.response import TemplateResponse

from GarageSale.models import EventData
from Billboard.models import BillboardLocations
from SaleLocation.models import SaleLocations
from datetime import date
from collections import namedtuple


def event_stats(request, event_id=None):
    """"Provide stats for this given event - so far it is counts of Billboard and sales locations """

    def nice(inc):
        return ('+' if inc >= 0 else '') + str(inc)

    Stats_entry = namedtuple('Stats_entry', "name, total, increment")

    the_event = EventData.objects.get(id=event_id)
    stats_category = {'Advertising Billboards': BillboardLocations,
                      'Sales Locations': SaleLocations}

    stats = []
    for item, model in stats_category.items():
        total = model.objects.filter(event=the_event).count()
        yesterday = model.objects.filter(event_id=the_event, creation_date__lt=date.today()).count()

        entry = Stats_entry(name=item,
                            total=total,
                            increment=nice(total - yesterday))
        stats.append(entry)

    return TemplateResponse(request, "event/stats/event_stats.html",
                            context={'event_id': the_event.id,
                                     'stats': stats})
