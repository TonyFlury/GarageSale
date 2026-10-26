from django.db.models import OuterRef, Subquery
from decimal import Decimal

from Contributors.models import Contributor, ContributorEvent, Contributions


def confirmed_sponsors_for_event(event):
    """Public sponsors, including after the event, based on their latest status."""
    sponsors = Contributor.objects.filter(contributor_type="Sponsor")
    if event is None:
        return sponsors.none()
    latest_status = ContributorEvent.objects.filter(
        contributor_id=OuterRef("pk"), event_id=event.pk,
    ).order_by("-timestamp", "-pk").values("status")[:1]
    return sponsors.annotate(sponsor_status=Subquery(latest_status)).filter(
        sponsor_status="Confirmed",
    ).order_by("contributor_name", "pk")


def sponsor_wall_for_event(event):
    """Feature up to four confirmed sponsors by cash plus valued non-cash gifts."""
    sponsors = list(confirmed_sponsors_for_event(event))
    totals = {}
    if event is not None and sponsors:
        for sponsor_id, gift, cash, value in Contributions.objects.filter(
            contributor_id__in=[sponsor.pk for sponsor in sponsors], event_id=event.pk,
        ).values_list("contributor_id", "gift", "cash", "amount"):
            amount = Contributions(gift=gift, cash=cash, amount=value).monetary_value
            if amount is not None and amount > 0:
                totals[sponsor_id] = totals.get(sponsor_id, Decimal("0")) + amount
    ranked = sorted(sponsors, key=lambda sponsor: (
        -totals.get(sponsor.pk, Decimal("0")), sponsor.contributor_name.casefold(), sponsor.pk,
    ))
    headliners = {sponsor.pk for sponsor in ranked[:4] if totals.get(sponsor.pk, 0) > 0}
    for sponsor in sponsors:
        sponsor.wall_headliner = sponsor.pk in headliners
    return sponsors
