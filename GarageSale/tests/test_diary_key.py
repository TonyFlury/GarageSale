from datetime import date

from django.test import TestCase, override_settings

from Diary import api
from GarageSale.models import EventData


@override_settings(DIARY_PERMISSION_GROUPS={'use': ('Officer',), 'edit': ('Officer',)})
class EventDiaryKeyTests(TestCase):
    def test_event_stores_the_api_key_without_a_foreign_key(self):
        actor = api.Actor('officer', frozenset({'Officer'}))
        template = api.DiaryTemplate.create(actor=actor, name='Host event template').key
        version = api.DiaryTemplate.from_key(actor=actor, key=template).create_version(number=1).key
        api.DiaryTemplateVersion.from_key(actor=actor, key=version).approve()
        key = api.DiaryInstance.create(actor=actor, template_version_key=version, event_ref='host:event:1',
                                       name='Event calendar', event_year=2027, milestone_dates={}).key
        event = EventData.objects.create(event_date=date(2027, 6, 27), use_from=date(2027, 1, 1), diary_key=key)
        event.refresh_from_db()
        self.assertEqual(event.diary_key, key)
        self.assertFalse(EventData._meta.get_field('diary_key').is_relation)
