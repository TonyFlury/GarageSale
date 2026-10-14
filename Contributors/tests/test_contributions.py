import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import RequestFactory, SimpleTestCase
from django.db import DatabaseError
from django.urls import reverse

from Contributors.views.contributions import ContributionForm, add_contribution, delete_contribution


class AddContributionTests(SimpleTestCase):
    def setUp(self):
        atomic = patch("Contributors.views.contributions.transaction.atomic")
        self.atomic = atomic.start()
        self.addCleanup(atomic.stop)

    @patch("Contributors.views.contributions.logger")
    @patch("Contributors.views.contributions.render_to_string")
    @patch("Contributors.views.contributions.contributions_context", return_value={})
    @patch("Contributors.views.contributions.Contributions.objects.create")
    @patch("Contributors.views.contributions.get_current_contribution_event", return_value=SimpleNamespace(pk=23))
    @patch("Contributors.views.contributions.get_object_or_404")
    def test_server_failure_returns_explanation_and_exits_transaction_with_error(self, lookup, event, create, context, render, logger):
        for failure in (DatabaseError("Database unavailable"), RuntimeError("Template failure")):
            with self.subTest(failure=type(failure).__name__):
                create.return_value.pk = 42
                render.side_effect = failure
                response = add_contribution(self.request({"gift": "Voucher", "event_id": "23"}), pk=7)
                self.assertEqual(response.status_code, 500)
                message = json.loads(response.content)["errors"]["save"][0]["message"]
                self.assertIn("Nothing was saved", message)
                self.assertNotIn(str(failure), message)
                self.assertIs(self.atomic.return_value.__exit__.call_args.args[1], failure)
                logger.exception.assert_called()

    def request(self, data):
        request = RequestFactory().post(reverse("contributors:add_contribution", args=[7]), data)
        request.user = SimpleNamespace(is_authenticated=True)
        return request

    @patch("Contributors.views.contributions.render_to_string", return_value="Updated list")
    @patch("Contributors.views.contributions.contributions_context", return_value={})
    @patch("Contributors.views.contributions.get_object_or_404")
    def test_delete_scopes_contribution_to_contributor_and_current_event(self, lookup, context, render):
        from Contributors.models import Contributions
        contributor = SimpleNamespace(pk=7)
        contribution = SimpleNamespace(delete=Mock())
        lookup.side_effect = [contributor, contribution]
        request = self.request({"event_id": "23"})
        request.current_event = SimpleNamespace(pk=23)
        response = delete_contribution(request, pk=7, contribution_pk=42)
        self.assertEqual(response.status_code, 200)
        lookup.assert_called_with(Contributions, pk=42, contributor=contributor, event=request.current_event)
        contribution.delete.assert_called_once_with()
        self.assertEqual(json.loads(response.content)["contributions_html"], "Updated list")

    @patch("Contributors.views.contributions.get_object_or_404")
    def test_delete_rejects_stale_event_before_looking_up_contribution(self, lookup):
        request = self.request({"event_id": "22"})
        request.current_event = SimpleNamespace(pk=23)
        response = delete_contribution(request, pk=7, contribution_pk=42)
        self.assertEqual(response.status_code, 409)
        lookup.assert_not_called()

    @patch("Contributors.views.contributions.render_to_string", return_value="Updated gifts")
    @patch("Contributors.views.contributions.contributions_context", return_value={})
    @patch("Contributors.views.contributions.Contributions.objects.create")
    @patch("Contributors.views.contributions.get_current_contribution_event")
    @patch("Contributors.views.contributions.get_object_or_404")
    def test_saves_cash_and_non_cash_for_contributor_and_current_event(self, lookup, event, create, context, render):
        event.return_value = SimpleNamespace(pk=23)
        create.return_value.pk = 42
        for cash in (False, True):
            with self.subTest(cash=cash):
                data = {"gift": "  Sponsorship donation  ", "event_id": "23"}
                if cash:
                    data["cash"] = "on"
                    data["gift"] = "£125.50"
                response = add_contribution(self.request(data), pk=7)
                self.assertEqual(response.status_code, 201)
                create.assert_called_with(
                    contributor=lookup.return_value, event=event.return_value,
                    gift="£125.50" if cash else "Sponsorship donation", cash=cash,
                )
                self.assertEqual(json.loads(response.content)["contributions_html"], "Updated gifts")

    @patch("Contributors.views.contributions.Contributions.objects.create")
    @patch("Contributors.views.contributions.get_current_contribution_event")
    @patch("Contributors.views.contributions.get_object_or_404")
    def test_missing_or_changed_current_event_does_not_save(self, lookup, event, create):
        for current_event in (None, SimpleNamespace(pk=24)):
            with self.subTest(event=current_event):
                event.return_value = current_event
                response = add_contribution(self.request({"gift": "Voucher", "event_id": "23"}), pk=7)
                self.assertEqual(response.status_code, 409)
        create.assert_not_called()

    @patch("Contributors.views.contributions.Contributions.objects.create")
    @patch("Contributors.views.contributions.get_object_or_404")
    def test_invalid_description_does_not_save(self, lookup, create):
        for gift in ("", "  ", "x" * 1001):
            with self.subTest(gift=gift):
                response = add_contribution(self.request({"gift": gift, "event_id": "23"}), pk=7)
                self.assertEqual(response.status_code, 400)
        create.assert_not_called()

    def test_event_id_is_required(self):
        self.assertFalse(ContributionForm({"gift": "Voucher"}).is_valid())

    def test_cash_amount_is_validated_and_formatted(self):
        for value, expected in (("25", "£25.00"), ("£12.5", "£12.50")):
            form = ContributionForm({"gift": value, "cash": "on", "event_id": "23"})
            self.assertTrue(form.is_valid(), form.errors)
            self.assertEqual(form.cleaned_data["gift"], expected)
        for value in ("Voucher", "-5", "0", "12.345", "NaN", "Infinity"):
            form = ContributionForm({"gift": value, "cash": "on", "event_id": "23"})
            self.assertFalse(form.is_valid())
            self.assertIn("gift", form.errors)

    def test_requires_login_and_post(self):
        request = self.request({})
        request.user.is_authenticated = False
        self.assertEqual(add_contribution(request, pk=7).status_code, 302)
        request = RequestFactory().get("/")
        request.user = SimpleNamespace(is_authenticated=True)
        self.assertEqual(add_contribution(request, pk=7).status_code, 405)
