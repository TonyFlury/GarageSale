from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from Contributors.models import Contributor, Contributions
from GarageSale.models import EventData, PrizeDrawWinner
from GarageSale.views.prize_draw_views import prize_draw


class PublicPrizeDrawTests(TestCase):
    def setUp(self):
        self.event = EventData.objects.create(event_date=timezone.localdate() + timedelta(days=30), use_from=timezone.localdate() - timedelta(days=1))
        self.other_event = EventData.objects.create(event_date=timezone.localdate() - timedelta(days=365), use_from=timezone.localdate() - timedelta(days=400))
        self.sponsor = Contributor.objects.create(contributor_type="Sponsor", contributor_name="Example sponsor")

    def prize(self, gift, **kwargs):
        values = {"contributor": self.sponsor, "event": self.event, "cash": False,
                  "classification": "prize_draw", "gift": gift, **kwargs}
        return Contributions.objects.create(**values)

    def request(self, event):
        request = RequestFactory().get(reverse("PrizeDraw"))
        request.current_event = event
        request.user = AnonymousUser()
        return request

    def test_public_list_uses_event_classification_and_saved_order(self):
        second = self.prize("Second prize", position=2)
        first = self.prize("First <prize>", position=1)
        self.prize("Tombola only", classification="tombola")
        self.prize("Not allocated", classification="unclassified")
        self.prize("Cash only", cash=True)
        self.prize("Previous event prize", event=self.other_event)
        response = prize_draw(self.request(self.event))
        self.assertEqual(list(response.context_data["prizes"]), [first, second])
        html = self.client.get(reverse("PrizeDraw"))
        self.assertEqual(html.status_code, 200)
        self.assertContains(html, "First &lt;prize&gt;")
        self.assertLess(html.content.index(b"First &lt;prize&gt;"), html.content.index(b"Second prize"))
        for excluded in ("Tombola only", "Not allocated", "Cash only", "Previous event prize", "DeLonghi"):
            self.assertNotContains(html, excluded)

    def test_reordering_is_reflected_on_next_request_and_winner_details_are_not_public(self):
        first = self.prize("Meal voucher", position=1)
        second = self.prize("Hamper", position=2)
        PrizeDrawWinner.objects.create(contribution=first, name="Private winner name", ticket_number="00007",
                                      phone="Private phone", address="Private address")
        first.position = 3
        first.save(update_fields=["position"])
        self.assertEqual(list(prize_draw(self.request(self.event)).context_data["prizes"]), [second, first])
        response = self.client.get(reverse("PrizeDraw"))
        for private in ("Private winner name", "Private phone", "Private address", "00007"):
            self.assertNotContains(response, private)

    def test_empty_allocation_has_placeholder(self):
        self.assertContains(self.client.get(reverse("PrizeDraw")), "Prizes will be announced here as they are allocated.")
        self.assertFalse(prize_draw(self.request(self.event)).context_data["draw_complete"])

    @patch("GarageSale.views.prize_draw_views.get_current_contribution_event", return_value=None)
    def test_no_current_event_does_not_show_unassigned_prizes(self, current):
        self.prize("Unassigned prize", event=None)
        response = prize_draw(self.request(None))
        self.assertEqual(list(response.context_data["prizes"]), [])

    @patch("GarageSale.views.prize_draw_views.get_current_contribution_event")
    def test_event_fallback(self, current):
        current.return_value = self.event
        prize = self.prize("Fallback prize")
        self.assertEqual(list(prize_draw(self.request(None)).context_data["prizes"]), [prize])

    def test_year_sales_opening_draw_and_notification_dates_follow_the_event(self):
        from datetime import date
        self.event.event_date = date(2030, 6, 30)
        self.event.open_sales_bookings = date(2030, 3, 20)
        self.event.save(update_fields=["event_date", "open_sales_bookings"])
        response = self.client.get(reverse("PrizeDraw"))
        self.assertContains(response, "2030 Prize Draw")
        self.assertContains(response, "Wednesday 20th March 2030")
        self.assertContains(response, "Sunday 30th June 2030")
        self.assertContains(response, "7th July 2030")
        self.assertContains(response, "2030 fundraising campaign")
        self.assertNotContains(response, "2026")

    def test_notification_deadline_handles_year_boundary(self):
        from datetime import date
        self.event.event_date = date(2030, 12, 29)
        response = prize_draw(self.request(self.event))
        self.assertEqual(response.context_data["winner_notification_date"], date(2031, 1, 5))

    def test_prizes_include_random_conjunction_and_escaped_sponsor_name(self):
        self.sponsor.contributor_name = "Oak & <Co>"
        self.sponsor.save(update_fields=["contributor_name"])
        self.prize("A <voucher>")
        for conjunction in ("donated by", "provided by", "courtesy of"):
            with self.subTest(conjunction=conjunction), patch(
                "GarageSale.views.prize_draw_views.random.choice", return_value=conjunction,
            ) as choose:
                response = self.client.get(reverse("PrizeDraw"))
                self.assertContains(response, f"A &lt;voucher&gt; {conjunction} Oak &amp; &lt;Co&gt;")
                choose.assert_called_once_with(("donated by", "provided by", "courtesy of"))

    def test_all_tickets_publish_names_and_tickets_but_never_contact_details(self):
        first = self.prize("Meal voucher", position=1)
        second = self.prize("Hamper", position=2)
        PrizeDrawWinner.objects.create(contribution=first, name="Alex <Smith>", ticket_number="00007", phone="PRIVATE PHONE", address="PRIVATE ADDRESS")
        response = self.client.get(reverse("PrizeDraw"))
        self.assertNotContains(response, "Alex &lt;Smith&gt;")
        self.assertNotContains(response, "00007")
        PrizeDrawWinner.objects.create(contribution=second, name="Sam Jones", ticket_number="00008", phone="ANOTHER PRIVATE PHONE", address="ANOTHER PRIVATE ADDRESS")
        response = self.client.get(reverse("PrizeDraw"))
        self.assertContains(response, "Prizes and Winners")
        self.assertContains(response, "Alex &lt;Smith&gt;")
        self.assertContains(response, "Sam Jones")
        self.assertContains(response, "00007")
        self.assertContains(response, "00008")
        self.assertNotContains(response, "PRIVATE PHONE")
        self.assertNotContains(response, "PRIVATE ADDRESS")
        self.assertLess(response.content.index(b"00007"), response.content.index(b"00008"))

    def test_recorded_ticket_with_pending_name_shows_pending_label(self):
        prize = self.prize("Voucher")
        PrizeDrawWinner.objects.create(contribution=prize, ticket_number="00009")
        response = self.client.get(reverse("PrizeDraw"))
        self.assertContains(response, "00009")
        self.assertContains(response, "Winner name pending")

    def test_blank_tickets_and_excluded_contributions_do_not_publish_partial_results(self):
        first = self.prize("First")
        second = self.prize("Second")
        PrizeDrawWinner.objects.create(contribution=first, name="Alex", ticket_number="00010")
        pending = PrizeDrawWinner.objects.create(contribution=second, name="Sam", ticket_number="   ")
        self.assertFalse(prize_draw(self.request(self.event)).context_data["draw_complete"])
        pending.ticket_number = "00011"
        pending.save(update_fields=["ticket_number"])
        self.prize("Tombola", classification="tombola")
        self.prize("Cash", cash=True)
        self.prize("Other event", event=self.other_event)
        with self.assertNumQueries(2):
            response = prize_draw(self.request(self.event))
        self.assertTrue(response.context_data["draw_complete"])
