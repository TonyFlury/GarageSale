import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Permission
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from Contributors.models import Contributor, Contributions, ContributorHistory
from GarageSale.models import EventData
from Sponsors.contribution_board import ContributionBoard, board_queryset, board_revision
from TeamPageFramework.entry_point import get_entry_points


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ContributionBoardTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser("board@example.com", "password")
        self.event = EventData.objects.create(event_date=timezone.localdate() + timedelta(days=30), use_from=timezone.localdate() - timedelta(days=1))
        self.other_event = EventData.objects.create(event_date=timezone.localdate() - timedelta(days=365), use_from=timezone.localdate() - timedelta(days=400))
        self.sponsor = Contributor.objects.create(contributor_type="Sponsor", contributor_name="Acme <Co>")
        self.first = Contributions.objects.create(contributor=self.sponsor, event=self.event, gift="Voucher <one>")
        self.second = Contributions.objects.create(contributor=self.sponsor, event=self.event, gift="Voucher two")
        self.cash = Contributions.objects.create(contributor=self.sponsor, event=self.event, cash=True, gift="£100")
        self.other = Contributions.objects.create(contributor=self.sponsor, event=self.other_event, gift="Other event")
        marketer = Contributor.objects.create(contributor_type="Marketer", contributor_name="Other type")
        self.marketer = Contributions.objects.create(contributor=marketer, event=self.event, gift="Not a sponsor gift")
        self.url = reverse("TeamPages:ContributionBoard", args=[self.event.pk])

    def request(self, method="get", payload=None, user=None):
        if method == "post":
            request = RequestFactory().post(self.url, data=json.dumps(payload), content_type="application/json")
        else:
            request = RequestFactory().get(self.url)
        request.user = user or self.user
        request.current_event = self.event
        return ContributionBoard.as_view()(request, event_id=self.event.pk)

    def payload(self, prize=None, tombola=None, unclassified=None):
        return {"revision": board_revision(list(board_queryset(self.event))), "columns": {
            "unclassified": unclassified if unclassified is not None else [],
            "prize_draw": prize if prize is not None else [self.first.pk, self.second.pk],
            "tombola": tombola if tombola is not None else [],
        }}

    def test_defaults_and_board_scope(self):
        self.assertEqual(self.first.classification, "unclassified")
        response = self.request()
        columns = response.context_data["columns"]
        self.assertEqual([item.pk for item in columns[0]["items"]], [self.first.pk, self.second.pk])
        self.assertEqual(columns[1]["items"], [])
        self.assertTrue(response.context_data["can_edit"])

    def test_moves_and_reordering_are_saved_with_audit_history(self):
        response = self.request("post", self.payload())
        self.assertEqual(response.status_code, 200)
        self.first.refresh_from_db()
        self.assertEqual((self.first.classification, self.first.position), ("prize_draw", 1))
        self.second.refresh_from_db()
        self.assertEqual(self.second.position, 2)
        response = self.request("post", self.payload(prize=[self.second.pk], tombola=[self.first.pk]))
        self.assertEqual(response.status_code, 200)
        self.first.refresh_from_db()
        self.assertEqual((self.first.classification, self.first.position), ("tombola", 1))
        response = self.request("post", self.payload(prize=[self.second.pk, self.first.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(board_queryset(self.event).values_list("pk", flat=True)), [self.second.pk, self.first.pk])
        self.assertTrue(ContributorHistory.objects.filter(related_event=self.event, user=self.user, event_type="Organised").exists())
        self.cash.refresh_from_db()
        self.other.refresh_from_db()
        self.marketer.refresh_from_db()
        self.assertEqual([self.cash.classification, self.other.classification, self.marketer.classification], ["unclassified"] * 3)

    def test_stale_revision_and_added_items_do_not_overwrite_changes(self):
        stale = self.payload()
        self.assertEqual(self.request("post", stale).status_code, 200)
        self.assertEqual(self.request("post", stale).status_code, 409)
        fresh = self.payload()
        Contributions.objects.create(contributor=self.sponsor, event=self.event, gift="New gift")
        self.assertEqual(self.request("post", fresh).status_code, 409)

    def test_duplicates_foreign_cash_missing_and_invalid_classifications_are_rejected(self):
        for ids in ([self.first.pk, self.first.pk], [self.first.pk], [self.first.pk, self.cash.pk],
                    [self.first.pk, self.other.pk], [self.first.pk, self.marketer.pk], [True, self.second.pk]):
            with self.subTest(ids=ids):
                self.assertIn(self.request("post", self.payload(prize=ids)).status_code, [400, 409])
        for payload in ([], None, {"columns": {}}, {"revision": "bad", "columns": {"wrong": []}}):
            self.assertEqual(self.request("post", payload).status_code, 400)
        self.assertFalse(ContributorHistory.objects.filter(event_type="Organised").exists())

    def test_permissions_and_login_are_enforced(self):
        self.assertEqual(self.request(user=AnonymousUser()).status_code, 302)
        viewer = get_user_model().objects.create_user("viewer@example.com", "password")
        viewer.user_permissions.add(Permission.objects.get(content_type__app_label="Contributors", codename="view_contributions"))
        response = self.request(user=viewer)
        self.assertFalse(response.context_data["can_edit"])
        self.assertEqual(self.request("post", self.payload(), user=viewer).status_code, 403)

    def test_page_renders_and_entry_point_is_in_data_section(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Voucher &lt;one&gt;")
        self.assertContains(response, "Prize Draw")
        self.assertContains(response, 'class="contribution-move"')
        entries = list(get_entry_points(self.user, nav_page="TeamPagesData"))
        entry = next(entry for entry in entries if entry["name"] == "Prize Allocation")
        self.assertEqual(entry["url_path"], "TeamPages:ContributionBoard")
        self.assertIn("contribution-board.svg", entry["icon_path"])

    def test_historic_events_are_excluded_and_direct_access_is_rejected(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertNotIn(self.other_event, list(response.context_data["events"]))
        response = self.client.get(reverse("TeamPages:ContributionBoard"), {"event": self.other_event.pk})
        self.assertEqual(response.status_code, 404)
        historic_url = reverse("TeamPages:ContributionBoard", args=[self.other_event.pk])
        self.assertEqual(self.client.get(historic_url).status_code, 404)
        self.assertEqual(self.client.post(historic_url, data=json.dumps(self.payload()), content_type="application/json").status_code, 404)

    def test_event_today_is_available(self):
        self.event.event_date = timezone.localdate()
        self.event.save(update_fields=["event_date"])
        self.assertEqual(self.request().status_code, 200)

    def test_picker_is_hidden_for_one_event_and_shown_for_multiple(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertNotContains(response, 'id="contribution-board-event"')
        self.assertContains(response, str(self.event))
        EventData.objects.create(event_date=timezone.localdate() + timedelta(days=90), use_from=timezone.localdate())
        self.assertContains(self.client.get(self.url), 'id="contribution-board-event"')
