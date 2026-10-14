from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.forms import modelform_factory
from django.utils import timezone

from Contributors.models import Contributor, Contributions
from GarageSale.models import EventData, PrizeDrawWinner


class PrizeDrawWinnerTests(TestCase):
    def setUp(self):
        self.event = EventData.objects.create(event_date=timezone.localdate() + timedelta(days=30), use_from=timezone.localdate())
        self.sponsor = Contributor.objects.create(contributor_type="Sponsor", contributor_name="Voucher donor")
        self.prize = Contributions.objects.create(contributor=self.sponsor, event=self.event, gift="Meal for two", classification="prize_draw")

    def test_winner_preserves_ticket_number_and_contact_details_are_optional(self):
        winner = PrizeDrawWinner(contribution=self.prize, name="Alex Smith", ticket_number="00042")
        winner.full_clean()
        winner.save()
        winner.refresh_from_db()
        self.assertEqual(winner.ticket_number, "00042")
        self.assertEqual((winner.phone, winner.address), ("", ""))
        self.assertEqual(self.prize.prize_draw_winner, winner)
        self.assertEqual(winner.contribution.event, self.event)

    def test_contact_details_can_be_recorded(self):
        winner = PrizeDrawWinner.objects.create(contribution=self.prize, name="Alex Smith", ticket_number="Blue A-42",
                                               phone="+44 1632 960001", address="1 Example Street\nExample Town")
        winner.refresh_from_db()
        self.assertEqual(winner.phone, "+44 1632 960001")
        self.assertIn("\n", winner.address)
        self.assertIn("Blue A-42", str(winner))

    def test_only_one_winner_per_prize(self):
        PrizeDrawWinner.objects.create(contribution=self.prize, name="Alex", ticket_number="42")
        with self.assertRaises(IntegrityError), transaction.atomic():
            PrizeDrawWinner.objects.create(contribution=self.prize, name="Sam", ticket_number="43")

    def test_ticket_is_required_but_name_can_be_pending(self):
        with self.assertRaises(ValidationError) as error:
            PrizeDrawWinner(contribution=self.prize).full_clean()
        self.assertNotIn("name", error.exception.message_dict)
        self.assertIn("ticket_number", error.exception.message_dict)

    def test_non_prize_draw_and_cash_contributions_are_rejected(self):
        for cash, classification in ((True, "prize_draw"), (False, "tombola"), (False, "unclassified")):
            with self.subTest(cash=cash, classification=classification):
                contribution = Contributions.objects.create(contributor=self.sponsor, event=self.event,
                                                            cash=cash, classification=classification)
                with self.assertRaises(ValidationError):
                    PrizeDrawWinner(contribution=contribution, name="Alex", ticket_number="42").full_clean()

    def test_model_form_offers_only_non_cash_prize_draw_items(self):
        other = Contributions.objects.create(contributor=self.sponsor, event=self.event, classification="tombola")
        form = modelform_factory(PrizeDrawWinner, fields="__all__")()
        self.assertIn(self.prize, form.fields["contribution"].queryset)
        self.assertNotIn(other, form.fields["contribution"].queryset)
