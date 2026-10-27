"""Reusable query adapters and event comparisons for the SVG dashboard.

Add QueryMetric definitions in views/dashboard.py. Each adapter emits grouped
``event_id/day/value/records`` rows; dates are local calendar dates, not UTC
midnight buckets. The browser consumes build_metric()'s model-independent JSON.
Short completed campaigns remain in all later comparisons at their final total.
"""
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Callable

from django.db.models import Count, Q
from django.db.models.functions import TruncDate


@dataclass(frozen=True)
class QueryMetric:
    """A query, its campaign clock and presentation metadata.

    queryset is a zero-argument callable returning one row per counted record.
    timestamp may be a DateTimeField or a queryset DateTime annotation; start_field
    names an EventData date. aggregate returns Count/Sum/etc. value_field, when
    supplied, makes missing numeric amounts explicit instead of summing as zero.
    event_field identifies the query's event foreign key. The renderer has no
    metric-specific branches: label/unit/precision/colour describe presentation.
    """
    key: str
    label: str
    queryset: Callable
    timestamp: str
    start_field: str
    aggregate: Callable
    colour: str
    description: str
    unit: str = ''
    precision: int = 0
    count_label: str = 'recorded for this event'
    value_field: str | None = None
    event_field: str = 'event_id'

    def load(self, events):
        """Return daily buckets with one query, regardless of event count."""
        query = self.queryset().filter(**{f'{self.event_field}__in': [e.pk for e in events]})
        annotations = {'value': self.aggregate(), 'records': Count('pk')}

        # Preserve unknown numeric values rather than treating them as zero.
        if self.value_field:
            annotations['missing_values'] = Count('pk', filter=Q(**{f'{self.value_field}__isnull': True}))

        # Clear model ordering so it cannot accidentally enlarge the GROUP BY.
        rows = query.order_by().annotate(day=TruncDate(self.timestamp)).values(
            self.event_field, 'day').annotate(**annotations)
        grouped = defaultdict(list)

        # Materialise only daily aggregates, never every underlying model row.
        for row in rows:
            grouped[row[self.event_field]].append(row)
        return grouped


@dataclass
class Campaign:
    """An observed campaign; None denotes unknown rather than a zero total."""
    start: date | None
    total: float | None
    values: list[float] | None
    warnings: list[str]


def daily_buckets(rows, start, end):
    """Sum in-window rows and retain separate counts of missing data."""
    daily, total = defaultdict(Decimal), Decimal(0)
    undated = missing = 0

    # Unknown dates contribute to final totals, but cannot support a dated curve.
    for row in rows:
        day = row['day']

        # Applications outside this event's campaign never enter its counts.
        if day is not None and not start <= day <= end:
            continue
        value = row['value'] or Decimal(0)
        total += value
        missing += row.get('missing_values', 0)

        # Keep missing-date records distinct from dated zero-activity days.
        if day is None:
            undated += row['records']
        else:
            daily[day] += value
    return daily, total, undated, missing


def data_warnings(undated, missing):
    """Explain unavailable curves and totals without hiding partial data."""
    warnings = []

    # A known final amount must not create an invented historical date.
    if undated:
        warnings.append(f'{undated} record(s) have no recorded date; totals include them, but run rates are unavailable.')

    # SUM ignores NULL; warn instead of displaying that partial sum as complete.
    if missing:
        warnings.append(f'{missing} cash record(s) have no numeric amount; the total and run rate are unavailable.')
    return warnings


def running_totals(daily, start, end):
    """Include day 0 and every inactive day, retaining decimal precision in sums."""
    values, running = [], Decimal(0)

    # Zero additions on quiet days produce the expected flat cumulative segment.
    for offset in range((end - start).days + 1):
        running += daily[start + timedelta(days=offset)]
        values.append(float(running))
    return values


def campaign(metric, event, rows, snapshot):
    """Build a campaign using its own opening date, capped at snapshot/event day."""
    start = getattr(event, metric.start_field)

    # Invalid configuration is unknown, not an empty successful campaign.
    if start is None or start > event.event_date:
        return Campaign(start, None, None, ['Opening date is missing or after the event date.'])
    end = min(event.event_date, snapshot)

    # A not-yet-open campaign has no comparable elapsed day.
    if end < start:
        return Campaign(start, 0, None, ['Applications/reporting have not opened yet.'])
    daily, total, undated, missing = daily_buckets(rows, start, end)
    warnings = data_warnings(undated, missing)
    values = running_totals(daily, start, end)
    return Campaign(start, None if missing else float(total), None if missing or undated else values, warnings)


def at(values, day):
    """Carry completed campaigns forward at their final cumulative value."""
    return values[min(day, len(values) - 1)]


def average(values):
    """No comparable events means unknown, not a zero benchmark."""
    return sum(values) / len(values) if values else None


def comparison_row(day, current, history):
    """The maximum is pointwise; it need not belong to one particular event."""
    return {'day': day, 'current': current, 'average': average(history),
            'maximum': max(history) if history else None}


def cumulative_rows(current, historical):
    """Align each historical curve by elapsed days, not calendar dates."""
    return [comparison_row(day, value, [at(series, day) for series in historical])
            for day, value in enumerate(current)]


def additions(values, day, before):
    """Subtract actual cumulative endpoints, including short campaign plateaus."""
    return at(values, day) - (at(values, before) if before is not None else 0)


def weekly_row_at(current, historical, day):
    """Precompute a week's progress at any replay day, including partial weeks.

    Maxima must use individual campaigns' additions, not differences between
    cumulative maxima. Shipping these rows makes replay entirely query-free.
    """
    before = ((day - 1) // 7) * 7 if day > 0 else None
    history = [additions(series, day, before) for series in historical]
    return comparison_row(day, additions(current, day, before), history) | {
        'fromDay': before, 'partial': before is not None and day - before < 7}


def weekly_rows(current, historical):
    """Day 0 is separate; the last interval is explicitly partial when needed."""
    last = len(current) - 1
    checkpoints = list(range(0, last + 1, 7))

    # Retain this week's progress even when a complete seven days has not elapsed.
    if checkpoints[-1] != last:
        checkpoints.append(last)
    return [weekly_row_at(current, historical, day) for day in checkpoints]


def presentation(metric):
    """Presentation-only part of the JSON contract shared by every metric."""
    return {'id': metric.key, 'label': metric.label, 'unit': metric.unit, 'precision': metric.precision,
            'colour': metric.colour, 'countLabel': metric.count_label, 'description': metric.description}


def benchmarks(current, historical):
    """Separate final and dated sample sizes when historical data is incomplete."""
    final = [c.total for _, c in historical if c.total is not None]
    dated = [c.values for _, c in historical if c.values is not None]
    comparable = [at(series, len(current.values) - 1) for series in dated] if current.values else []
    benchmark = average(comparable)
    difference = ((current.total / benchmark - 1) * 100
                  if current.total is not None and benchmark is not None and benchmark > 0 else None)
    return dated, {'finalAverage': average(final), 'finalMaximum': max(final) if final else None,
                   'comparableAverage': benchmark, 'differencePercent': difference,
                   'finalSample': len(final), 'comparableSample': len(dated)}


def build_metric(metric, event, previous, snapshot, grouped):
    """Produce one complete JSON metric for the unchanged template and JS.

    Numeric fields are finite numbers or null. cumulative/weekly contain day,
    current, average, maximum; weekly adds fromDay/partial. Missing history is
    null, valid zero activity is 0. weeklyToDate includes partial-week comparisons
    at every stopping day for query-free replay. Warnings explain excluded data.
    """
    current = campaign(metric, event, grouped.get(event.pk, []), snapshot)
    historical = [(e, campaign(metric, e, grouped.get(e.pk, []), e.event_date)) for e in previous]
    dated, comparisons = benchmarks(current, historical)
    days = max(0, (min(snapshot, event.event_date) - current.start).days) if current.start else 0
    historical_warnings = [f'{e.event_date}: {warning}' for e, c in historical for warning in c.warnings]
    return presentation(metric) | comparisons | {
        'start': current.start.isoformat() if current.start else None, 'days': days, 'total': current.total,
        'warnings': current.warnings, 'historicalWarnings': historical_warnings,
        'cumulative': cumulative_rows(current.values, dated) if current.values else [],
        'weekly': weekly_rows(current.values, dated) if current.values else [],
        'weeklyToDate': [weekly_row_at(current.values, dated, day)
                         for day in range(len(current.values))] if current.values else [],
    }
