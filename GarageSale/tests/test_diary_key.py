from datetime import date

from django.test import TestCase, override_settings

from Diary import api
from GarageSale.models import EventData


@override_settings(DIARY_PERMISSION_GROUPS={'use': ('Officer',), 'edit': ('Officer',)})
class EventDiaryKeyTests(TestCase):
    def test_event_stores_the_api_key_without_a_foreign_key(self):
        actor = api.Actor('officer', frozenset({'Officer'}))
        template = api.create_template(actor=actor, name='Host event template')
        version = api.create_template_version(actor=actor, template_key=template, number=1)
        api.approve_template_version(actor=actor, template_version_key=version)
        key = api.create_calendar(actor=actor, template_version_key=version, event_ref='host:event:1',
                                  name='Event calendar', event_year=2027, milestone_dates={})
        event = EventData.objects.create(event_date=date(2027, 6, 27), use_from=date(2027, 1, 1), diary_key=key)
        event.refresh_from_db()
        self.assertEqual(event.diary_key, key)
        self.assertFalse(EventData._meta.get_field('diary_key').is_relation)
