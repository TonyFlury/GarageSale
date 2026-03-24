"""
    File : stats_view.py

    Statistics view functions

"""

from collections import namedtuple, defaultdict
from datetime import date

import datetime

from django.db.models import F
from django.http import HttpResponse
from django.shortcuts import render
from django.templatetags.static import static

from GarageSale.models import EventData
from Location.models import Location
from TeamPageFramework.entry_point import register
import csv

import matplotlib
import matplotlib.pyplot as plt, mpld3

register('Ad Board Applications', 'Location:EventAdBoard',
         static('GarageSale/images/icons/navigation/ad-board-svgrepo-com.svg'),
         permission='GarageSale.is_team_member',
         needs_event=False, nav_page='TeamPagesData')
def event_ad_board(request):
    events = EventData.objects.all().order_by('-event_date')
    return render(request, template_name='stats/ad_board_download.html', context={'event_list': events, 'event_id':request.current_event.id, 'data_type': 'Ad board list'})


def download_ad_board_csv(request, event_id=None):
    ts = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    if event_id is None:
        event_id = request.current_event.id
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

def date_range(start_date, end_date):
    for n in range(int ((end_date - start_date).days)):
        yield start_date + datetime.timedelta(n)

def create_plot( event_id,  _type:str=''):

    event = EventData.objects.get(id=event_id)

    match _type:
        case 'ad_board':
            filter_conditions = {'ad_board': True}
            value = 'ad_board_timestamp'
            title = 'Ad board applications'
            open_field = 'open_billboard_bookings'
        case 'sale':
            filter_conditions = {'sale_event': True}
            value = 'sale_timestamp'
            title = 'open_sales_bookings'
            open_field = 'open_sales_bookings'
        case _:
            return None

    running_total:dict[date, int] = {}
    data = Location.objects.filter(event__id = event_id, **filter_conditions).values(value).order_by(value)
    if len(data) == 0:
        return None

    last_date = data[0][value].date()
    total = 0
    for row in data:
        total += 1
        if row[value].date() not in running_total:
            running_total[row[value].date()] = total
        else:
            running_total[row[value].date()] += 1
        last_date = row[value].date()

    # Back fill the dates up to today only for current events.
    if last_date <= date.today() <= event.event_date:
        for d in date_range(last_date, date.today()):
            running_total[d] = total

    fig, ax = plt.subplots()
    ax.set_ylim(bottom=0, top=total*1.1)
    fig.set_size_inches(6,3)
    ax.plot(running_total.keys(), running_total.values())

    ax.set_title(title)
    ax.set_ylabel('Number of applications')
    ax.set_xlabel('Date')
    ax.grid(True)
    fig.subplots_adjust(bottom=0.2)
    return mpld3.fig_to_html(fig, no_extras=True)


register('Statistics','Location:EventStats',
         static('GarageSale/images/icons/navigation/statistics-svgrepo-com.svg'),
         'GarageSale.is_team_member', needs_event=False, nav_page='TeamPagesData')
def event_stats(request, event_id=None):
    """"Provide stats for this given event - so far it is counts of Billboard and sales locations """

    event_id = event_id or request.current_event.id

    def nice(inc):
        return ('+' if inc >= 0 else '') + str(inc)

    the_event = EventData.objects.get(id=event_id)

    if event_id is None:
        event_id = request.current_event.id

    ad_board_plot = create_plot(event_id, 'ad_board')
    sale_plot = create_plot(event_id, 'sale')

    return render(request, "stats/event_stats.html",
                            context={ 'event_list': EventData.objects.all().order_by('-event_date'),
                                'event_id': the_event.id,
                                'stats':{
                                'Ad Boards': ad_board_plot,
                                'Sales locations': sale_plot,},
                                'data_type': 'Event stats'})
