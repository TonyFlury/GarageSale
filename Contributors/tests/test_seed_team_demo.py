"""Exercise the demo command against an isolated database and media directory."""
from datetime import timedelta
from decimal import Decimal
from io import StringIO
from tempfile import TemporaryDirectory
from xml.etree import ElementTree

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone

from Contributors.models import Contributor, ContributorEvent, ContributorHistory, Contributions
from GarageSale.models import EventData


class TeamDemoTests(TestCase):
    def setUp(self):
        self.media = TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        self.settings_override = override_settings(MEDIA_ROOT=self.media.name)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        today = timezone.localdate()
        self.event = EventData.objects.create(event_date=today + timedelta(days=30), use_from=today - timedelta(days=1))
        self.previous = EventData.objects.create(event_date=today - timedelta(days=1), use_from=today - timedelta(days=40))

    def seed(self, *args):
        with self.captureOnCommitCallbacks(execute=True):
            call_command("seed_team_demo", *args, stdout=StringIO())

    def test_requested_scenario_and_logos(self):
        self.seed()
        sponsors = Contributor.objects.filter(contributor_type="Sponsor")
        traders = Contributor.objects.filter(contributor_type="Marketer")
        self.assertEqual(sponsors.count(), 8)
        self.assertEqual(traders.count(), 4)
        contacted = sponsors.filter(contributorhistory__event_category="Contact").distinct()
        self.assertEqual(contacted.count(), 4)
        self.assertEqual(ContributorHistory.objects.count(), 6)
        self.assertTrue(all(timezone.localdate(note.timestamp) > self.previous.event_date
                            for note in ContributorHistory.objects.all()))
        self.assertEqual(ContributorEvent.objects.filter(event=self.event, status="Confirmed").count(), 2)
        self.assertEqual(ContributorEvent.objects.filter(event=self.event, status="Invited").count(), 2)
        self.assertEqual(Contributions.objects.get(cash=True).amount, Decimal("250"))
        self.assertEqual(Contributions.objects.get(cash=False).amount, Decimal("50"))
        self.assertEqual(Contributions.objects.get(cash=False).classification, "prize_draw")
        for sponsor in sponsors:
            self.assertTrue(sponsor.icon.storage.exists(sponsor.icon.name))
            with sponsor.icon.open("rb") as logo:
                self.assertEqual(ElementTree.fromstring(logo.read()).tag, "{http://www.w3.org/2000/svg}svg")
        self.assertFalse(traders.exclude(icon="").exists())

    def test_reruns_do_not_duplicate_records_or_overwrite_edits(self):
        self.seed()
        contributor = Contributor.objects.first()
        contributor.contact_name = "Edited in demonstration"
        contributor.save()
        before = {model: list(model.objects.order_by("pk").values())
                  for model in (Contributor, ContributorEvent, ContributorHistory, Contributions)}
        self.seed()
        for model, values in before.items():
            self.assertEqual(list(model.objects.order_by("pk").values()), values)

    def test_dry_run_creates_neither_records_nor_logos(self):
        self.seed("--dry-run")
        self.assertFalse(Contributor.objects.exists())
        self.assertFalse(ContributorHistory.objects.exists())
        self.assertFalse(ContributorEvent.objects.exists())
        self.assertFalse(Contributions.objects.exists())
        from pathlib import Path
        self.assertEqual(list(Path(self.media.name).iterdir()), [])

    def test_reserved_name_collision_leaves_real_record_unchanged(self):
        real = Contributor.objects.create(contributor_name="[TEAM DEMO] Alder Hardware", contributor_type="Sponsor")
        with self.assertRaisesMessage(CommandError, "Reserved demo name"):
            self.seed()
        self.assertEqual(list(Contributor.objects.all()), [real])
        self.assertFalse(ContributorHistory.objects.exists())

    def test_missing_or_expired_current_event_has_clear_error(self):
        self.event.use_from = timezone.localdate()
        self.event.save()
        with self.assertRaisesMessage(CommandError, "current event has passed"):
            self.seed()
        EventData.objects.all().delete()
        with self.assertRaisesMessage(CommandError, "No current event"):
            self.seed()

    def test_unknown_attribution_user_does_not_create_records(self):
        with self.assertRaisesMessage(CommandError, "No user exists"):
            self.seed("--user-email", "unknown@example.invalid")
        self.assertFalse(Contributor.objects.exists())
