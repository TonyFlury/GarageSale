"""Ad-board application list and CSV export for the team pages."""

import csv
import datetime

from django.http import HttpResponse
from django.shortcuts import render
from django.core.exceptions import PermissionDenied
from django.templatetags.static import static

from GarageSale.models import EventData
from Location.models import Location
from TeamPageFramework.entry_point import register

def require_report_access(user, export=False):
    permission = 'GarageSale.export_location' if export else 'Location.view_location'
    if not user.has_perm(permission):
        raise PermissionDenied('You do not have permission to access this report.')

register('Ad Board Applications', 'Location:EventAdBoard',
         static('GarageSale/images/icons/navigation/ad-board-svgrepo-com.svg'),
         permission='Location.view_location',
         needs_event=False, nav_page='TeamPagesData')
def event_ad_board(request):
    require_report_access(request.user)
    events = EventData.objects.all().order_by('-event_date')
    return render(request, template_name='stats/ad_board_download.html', context={'event_list': events, 'event_id':request.current_event.id, 'data_type': 'Ad board list'})


def download_ad_board_csv(request, event_id=None):
    require_report_access(request.user, export=True)
    ts = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    if event_id is None:
        event_id = request.current_event.id if request.current_event else None
    # We might need an error thingy here
    event = EventData.objects.get(id=event_id)
    qs = Location.objects.filter(event__id=event_id, ad_board=True)
    response = HttpResponse(content_type='text/csv',
                            headers={"Content-Disposition": f'attachment; filename="advert_boards-{event.event_date}_{ts}.csv"'}, )

    writer = csv.writer(response)
    writer.writerow(['Name', 'Address', 'Postcode', 'Phone'])
    for entry in qs:
        writer.writerow([f'{entry.user.full_name()}',
                         f'{entry.full_address()}',
                         f'{entry.postcode}',
                         f'{entry.user.phone}'])
    return response
