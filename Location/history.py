from django.db.models import Exists, OuterRef

from .models import Location


ADDRESS_FIELDS = ('house_number', 'street_name', 'town', 'postcode')


def available_historic_locations(user, event):
    if event is None:
        return Location.objects.none()
    current = Location.objects.filter(
        user=user, event=event,
        **{field: OuterRef(field) for field in ADDRESS_FIELDS},
    )
    return (Location.objects.filter(user=user, event__event_date__lt=event.event_date)
            .alias(already_added=Exists(current)).filter(already_added=False)
            .select_related('event').order_by('-event__event_date', 'postcode', 'pk'))
