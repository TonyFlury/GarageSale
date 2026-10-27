import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from Contributors.models import Contributor, Contributions
from GarageSale.models import EventData, PrizeDrawWinner
from GarageSale.views.prize_draw_views import winner_revision
from TeamPageFramework.entry_point import get_entry_points


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class PrizeDrawWinnerEntryTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser("draw@example.com", "password")
        self.client.force_login(self.user)
        self.event = EventData.objects.create(event_date=timezone.localdate() + timedelta(days=30), use_from=timezone.localdate() - timedelta(days=1))
        self.other_event = EventData.objects.create(event_date=timezone.localdate() - timedelta(days=365), use_from=timezone.localdate() - timedelta(days=400))
        self.sponsor = Contributor.objects.create(contributor_type="Sponsor", contributor_name="Sponsor <Co>")
        self.prize = Contributions.objects.create(contributor=self.sponsor, event=self.event, gift="Voucher <one>", classification="prize_draw", position=1)
        self.second = Contributions.objects.create(contributor=self.sponsor, event=self.event, gift="Voucher two", classification="prize_draw", position=2)
        self.url = reverse("TeamPages:PrizeDrawWinners", args=[self.event.pk])

    def post(self, action="ticket", revision=None, contribution=None, **values):
        data = {"action": action, "revision": revision if revision is not None else winner_revision(PrizeDrawWinner.objects.filter(contribution=self.prize).first()),
                "contribution_id": contribution or self.prize.pk, **values}
        return self.client.post(self.url, json.dumps(data), content_type="application/json")

    def test_page_lists_prizes_in_order_with_contact_fields_initially_disabled(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="winner-details-fields" disabled')
        self.assertContains(response, "Voucher &lt;one&gt;")
        self.assertLess(response.content.index(b"Voucher &lt;one&gt;"), response.content.index(b"Voucher two"))
        self.assertNotContains(response, 'id="winner-event"')
        entries = list(get_entry_points(self.user, nav_page="Prizes"))
        self.assertTrue(any(entry["name"] == "Prize Draw Winners" for entry in entries))

    def test_recording_ticket_persists_before_unlocking_details(self):
        response = self.post(ticket_number="00007")
        self.assertEqual(response.status_code, 200)
        winner = PrizeDrawWinner.objects.get(contribution=self.prize)
        self.assertEqual((winner.ticket_number, winner.name), ("00007", ""))
        self.assertTrue(response.json()["winner"]["ticket_recorded"])
        response = self.client.get(self.url)
        first = response.context_data["rows"][0]
        self.assertTrue(first["ticket_recorded"])
        self.assertFalse(response.context_data["rows"][1]["ticket_recorded"])
        self.assertEqual(len(response.context_data["events"]), 1)

    def test_contact_details_are_rejected_before_ticket_and_name_required_after(self):
        response = self.post("details", name="Alex", phone="01632960000", address="Example address")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(PrizeDrawWinner.objects.exists())
        self.assertEqual(self.post(ticket_number="42").status_code, 200)
        response = self.post("details", name="", phone="", address="")
        self.assertEqual(response.status_code, 400)
        self.assertIn("name", response.json()["errors"])

    def test_saving_and_editing_contact_details_preserves_ticket(self):
        self.post(ticket_number="Blue-0007")
        response = self.post("details", name="Alex Smith", phone="+44 1632 960001", address="1 Example Street\nExample Town")
        self.assertEqual(response.status_code, 200)
        winner = PrizeDrawWinner.objects.get(contribution=self.prize)
        self.assertEqual(winner.ticket_number, "Blue-0007")
        self.assertEqual(winner.name, "Alex Smith")
        self.assertEqual(winner.address, "1 Example Street\nExample Town")
        response = self.post("details", name="Alex Jones", phone="", address="")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(PrizeDrawWinner.objects.count(), 1)

    def test_ticket_changes_require_confirmation_before_clearing_existing_details(self):
        self.post(ticket_number="7")
        self.post("details", name="Alex", phone="123", address="Example")
        self.assertEqual(self.post(ticket_number="8").status_code, 409)
        winner = PrizeDrawWinner.objects.get(contribution=self.prize)
        self.assertEqual((winner.ticket_number, winner.name), ("7", "Alex"))
        response = self.post(ticket_number="8", reset_details=True)
        self.assertEqual(response.status_code, 200)
        winner.refresh_from_db()
        self.assertEqual((winner.ticket_number, winner.name, winner.phone, winner.address), ("8", "", "", ""))

    def test_stale_ticket_or_contact_save_cannot_overwrite_another_user(self):
        self.assertEqual(self.post(ticket_number="7").status_code, 200)
        self.assertEqual(self.post(ticket_number="8", revision="new").status_code, 409)
        revision = winner_revision(PrizeDrawWinner.objects.get(contribution=self.prize))
        self.post("details", name="Alex", phone="", address="")
        self.assertEqual(self.post("details", revision=revision, name="Sam").status_code, 409)
        self.assertEqual(PrizeDrawWinner.objects.get(contribution=self.prize).name, "Alex")

    def test_invalid_tickets_and_malformed_requests_are_rejected(self):
        for ticket in ("", "   ", "x" * 51):
            self.assertEqual(self.post(ticket_number=ticket).status_code, 400)
        for payload in ([], None, {"action": "unknown"}, {"action": "ticket", "contribution_id": True, "revision": "new"}):
            self.assertEqual(self.client.post(self.url, json.dumps(payload), content_type="application/json").status_code, 400)
        self.assertFalse(PrizeDrawWinner.objects.exists())

    def test_non_prizes_cash_and_other_events_cannot_receive_winners(self):
        for cash, classification, event in ((True, "prize_draw", self.event), (False, "tombola", self.event),
                                             (False, "unclassified", self.event), (False, "prize_draw", self.other_event)):
            contribution = Contributions.objects.create(contributor=self.sponsor, event=event, cash=cash, classification=classification)
            self.assertEqual(self.post(contribution=contribution.pk, ticket_number="7").status_code, 404)
        self.assertFalse(PrizeDrawWinner.objects.exists())

    def test_view_only_users_cannot_save_and_anonymous_users_must_log_in(self):
        viewer = get_user_model().objects.create_user("viewer@example.com", "password")
        viewer.user_permissions.add(Permission.objects.get(content_type__app_label="GarageSale", codename="view_prizedrawwinner"))
        self.client.force_login(viewer)
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertEqual(self.post(ticket_number="7").status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_missing_csrf_token_is_rejected(self):
        from django.test import Client
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        response = client.post(self.url, json.dumps({"action": "ticket", "contribution_id": self.prize.pk,
                                                   "revision": "new", "ticket_number": "7"}), content_type="application/json")
        self.assertEqual(response.status_code, 403)

    def test_add_only_user_can_record_ticket_but_cannot_edit_existing_winner(self):
        user = get_user_model().objects.create_user("ticket-recorder@example.com", "password")
        user.user_permissions.add(*Permission.objects.filter(content_type__app_label="GarageSale",
            codename__in=["view_prizedrawwinner", "add_prizedrawwinner"]))
        self.client.force_login(user)
        response = self.post(ticket_number="0007")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["can_edit"])
        self.assertEqual(self.post("details", name="Alex").status_code, 403)
