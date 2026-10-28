"""Event dashboard: change metric queries here without changing the renderer."""
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, OuterRef, Subquery, Sum
from django.http import Http404
from django.shortcuts import render
from django.templatetags.static import static
from django.utils import timezone
from django.views.decorators.http import require_safe

from Contributors.models import Contributions, ContributorEvent
from GarageSale.dashboard import QueryMetric, build_metric
from GarageSale.models import EventData
from GarageSale.market_dashboard import build_market_pipeline
from Location.models import Location
from TeamPageFramework.entry_point import register


register('Dashboard', 'EventDashboard',
         static('GarageSale/images/icons/navigation/dashboard.svg'),
         permission='Location.view_location', needs_event=False, nav_page='Overview', order=10)


def confirmed_contributions():
    """Use the event-specific latest status, without multiplying contribution rows."""
    # A scalar subquery prevents repeated status entries multiplying cash/counts.
    latest = ContributorEvent.objects.filter(
        contributor_id=OuterRef('contributor_id'), event_id=OuterRef('event_id'),
    ).order_by('-timestamp', '-pk')
    return Contributions.objects.annotate(
        confirmation_status=Subquery(latest.values('status')[:1]),
        confirmed_at=Subquery(latest.values('timestamp')[:1]),
    ).filter(confirmation_status='Confirmed')


def dashboard_metrics():
    """A new query-backed category needs only another QueryMetric entry."""
    # Definitions alone choose models, clocks, aggregations and visual metadata.
    return [
        QueryMetric('cash', 'Cash contributions', lambda: confirmed_contributions().filter(cash=True),
                    'confirmed_at', 'use_from', lambda: Sum('amount'), '#2164b0',
                    'Cash amounts from confirmed contributors, dated by their event-specific confirmation; this is not a bank reconciliation.',
                    unit='£', precision=2, value_field='amount'),
        QueryMetric('noncash', 'Non-cash contributions', lambda: confirmed_contributions().filter(cash=False),
                    'confirmed_at', 'use_from', lambda: Count('pk'), '#ae5c10',
                    'One count per non-cash contribution from confirmed contributors, dated by event-specific confirmation; estimated values are ignored.'),
        QueryMetric('boards', 'Ad-board locations', lambda: Location.objects.filter(ad_board=True),
                    'ad_board_timestamp', 'open_billboard_bookings', lambda: Count('pk'), '#8152af',
                    'Active ad-board locations, dated by their ad-board application from bookings opening.'),
        QueryMetric('sales', 'Sales locations', lambda: Location.objects.filter(sale_event=True),
                    'sale_timestamp', 'open_sales_bookings', lambda: Count('pk'), '#167768',
                    'Active sales locations, dated by their sale application from bookings opening.'),
    ]


def select_event(request, events, today):
    """Honour the picker, then current event, next upcoming, or latest completed."""
    event_id = request.GET.get('event')

    # An explicit invalid selection is an error, never a silent event switch.
    if event_id is not None:
        selected = next((e for e in events if str(e.pk) == event_id), None)

        # Reject unknown IDs before accessing any event's contribution data.
        if selected is None:
            raise Http404('Event not found.')
        return selected
    current_id = getattr(getattr(request, 'current_event', None), 'pk', None)
    selected = next((e for e in events if e.pk == current_id), None)
    upcoming = [e for e in events if e.event_date >= today]
    return selected or (upcoming[-1] if upcoming else next(iter(events), None))


def dashboard_payload(selected, events, today):
    """Load campaigns and market milestones with a fixed number of queries."""
    metrics, previous = [], []

    # An empty installation renders a useful page without attempting queries.
    if selected:
        previous = [e for e in events if e.event_date < min(selected.event_date, today)]

        # Query cost grows with metrics, not with the number of previous events.
        for definition in dashboard_metrics():
            grouped = definition.load([selected, *previous])
            metrics.append(build_metric(definition, selected, previous, today, grouped))
        metrics.append(build_market_pipeline(selected, previous, today))
    return {'metrics': metrics, 'previousEvents': len(previous),
            'timeline': replay_timeline(selected, metrics, today)}


def replay_timeline(selected, metrics, today):
    """Replay one calendar date across all metrics, each with its own opening."""
    # Only completed events can be replayed; live dashboards retain today's view.
    if selected is None or selected.event_date >= today:
        return None
    end = selected.event_date.isoformat()
    starts = [metric['start'] for metric in metrics if metric['start'] and metric['start'] <= end]
    return {'start': min(starts), 'end': end} if starts else None


@login_required
@require_safe
def event_dashboard(request):
    """Read-only ExecMember dashboard; dates and records are never changed."""
    # Enforce the dashboard's explicit executive membership boundary.
    if not request.user.is_active or not request.user.groups.filter(name='ExecMember').exists():
        raise PermissionDenied('The event dashboard is available to ExecMember members.')
    today = timezone.localdate()
    events = list(EventData.objects.order_by('-event_date', '-pk'))
    selected = select_event(request, events, today)
    return render(request, 'dashboard/event_dashboard.html', {
        'event_list': events, 'selected_event': selected, 'snapshot': today,
        'days_to_go': (selected.event_date - today).days if selected else None,
        'dashboard_data': dashboard_payload(selected, events, today),
    })
