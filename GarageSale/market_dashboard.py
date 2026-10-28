"""Distinct trader milestones for the dashboard's overlaid Craft Market circle."""
from collections import Counter, defaultdict
from types import SimpleNamespace

from django.db.models import Count, F, Max, Min, Q
from django.db.models.functions import TruncDate

from Contributors.models import ContributorEvent
from CraftMarket.models import PitchPayment
from GarageSale.dashboard import QueryMetric, build_metric


STAGES = (('invited', 'Invited', '#2164b0'), ('accepted', 'Accepted', '#a16207'), ('paid', 'Fees paid', '#15803d'))
DESCRIPTION = ('Distinct traders for this event: invited, accepted and fees paid. Sectors share a starting point; '
               'accepted overlays invited, then paid overlays accepted. Historical markers count accepted-or-paid '
               'traders once per event, using their latest acceptance/payment status. Rejections and cancellations '
               'do not erase earlier milestones. Fees paid counts receipts or explicit legacy paid states; '
               'older acceptance records alone do not prove payment. The campaign starts at activation or '
               'the earliest recorded milestone, whichever is earlier.')


def load_market_milestones(events, snapshot):
    """Two queries regardless of the number of events or retained status changes."""
    ids = [event.pk for event in events]
    in_window = Q(timestamp__date__lte=F('event__event_date')) & Q(timestamp__date__lte=snapshot)
    acceptance = Q(status__in=['Fee Pending', 'Pending', 'Confirmed', 'Fee paid']) & in_window
    records = ContributorEvent.objects.filter(event_id__in=ids, contributor__contributor_type='Marketer').order_by().values(
        'event_id', 'contributor_id').annotate(
            invited=Min(TruncDate('timestamp'), filter=Q(status='Invited') & in_window),
            accepted=Min(TruncDate('timestamp'), filter=acceptance),
            latest_accepted=Max(TruncDate('timestamp'), filter=acceptance),
            legacy_paid=Min(TruncDate('timestamp'), filter=Q(status='Fee paid') & in_window),
        )
    grouped = defaultdict(dict)
    for row in records:
        grouped[row['event_id']][row['contributor_id']] = row
    # Actual payment dates can precede the day a manager enters the receipt.
    payments = PitchPayment.objects.filter(event_id__in=ids, contributor__contributor_type='Marketer',
        paid_on__lte=F('event__event_date')
    ).filter(paid_on__lte=snapshot).values('event_id', 'contributor_id', 'paid_on')
    for payment in payments:
        row = grouped[payment['event_id']].setdefault(payment['contributor_id'], {})
        row['paid'] = payment['paid_on']
    return grouped


def first_day(*days):
    known = [day for day in days if day is not None]
    return min(known) if known else None


def daily_rows(event_id, days):
    return [{'event_id': event_id, 'day': day, 'value': count, 'records': count}
            for day, count in Counter(day for day in days if day is not None).items()]


def build_market_pipeline(selected, previous, snapshot):
    records = load_market_milestones([selected, *previous], snapshot)
    # Invitations to a future event may precede its activation date. Retain their
    # actual dates by extending this metric's campaign clock to the first milestone.
    def campaign_event(event):
        days = [day for row in records.get(event.pk, {}).values()
                for key in ('invited', 'accepted', 'legacy_paid', 'paid') if (day := row.get(key)) is not None]
        start = min([event.use_from, *days])
        return SimpleNamespace(pk=event.pk, event_date=event.event_date, use_from=start)
    selected_clock = campaign_event(selected)
    # Events without any retained trader history cannot establish a zero baseline.
    history = [campaign_event(event) for event in previous if records.get(event.pk)]
    historical = {}
    for event in history:
        checkpoints = []
        for row in records[event.pk].values():
            days = [row.get(key) for key in ('latest_accepted', 'paid', 'legacy_paid') if row.get(key) is not None]
            checkpoints.append(max(days) if days else None)
        historical[event.pk] = daily_rows(event.pk, checkpoints)

    milestones = {name: [] for name, _, _ in STAGES}
    inferred_invites = inferred_acceptances = 0
    for row in records.get(selected.pk, {}).values():
        paid = row.get('paid') or row.get('legacy_paid')
        accepted = first_day(row.get('accepted'), paid)
        invited = first_day(row.get('invited'), accepted)
        if invited is not None and invited != row.get('invited'):
            inferred_invites += 1
        if accepted is not None and accepted != row.get('accepted'):
            inferred_acceptances += 1
        for name, day in (('invited', invited), ('accepted', accepted), ('paid', paid)):
            milestones[name].append(day)

    stages = []
    for name, label, colour in STAGES:
        definition = QueryMetric(f'market_{name}', label, ContributorEvent.objects.none, 'timestamp', 'use_from',
                                 lambda: Count('pk'), colour, DESCRIPTION, count_label=label.lower())
        grouped = {**historical, selected.pk: daily_rows(selected.pk, milestones[name])}
        stages.append(build_metric(definition, selected_clock, history, snapshot, grouped))
    metric = {**stages[1], 'id': 'market', 'label': 'Craft Market', 'kind': 'pipeline',
              'countLabel': 'confirmed places', 'stages': stages}
    if inferred_invites:
        metric['warnings'].append(f'{inferred_invites} trader(s) have acceptance/payment records without an earlier invitation; invitation progress includes these later-stage traders.')
    if inferred_acceptances:
        metric['warnings'].append(f'{inferred_acceptances} trader(s) have payments before a retained acceptance; acceptance progress includes their payment dates.')
    missing = len(previous)-len(history)
    if missing:
        metric['historicalWarnings'].append(f'{missing} previous event(s) have no retained Craft Market history and are excluded from its benchmarks.')
    return metric
