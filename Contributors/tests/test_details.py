import json
from contextlib import nullcontext
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, SimpleTestCase
from django.template.loader import render_to_string
from django.urls import reverse

from Contributors.models import Contributor
from Contributors.views.details import ContributorDetailsForm, contributor_details


class ContributorDetailsTests(SimpleTestCase):
    @patch("Contributors.views.details.get_object_or_404")
    def test_name_label_uses_spreadsheet_data_label(self, lookup):
        lookup.return_value = self.contributor
        response = contributor_details(self.request(data={"data_label": "Sponsor"}), pk=7)
        html = json.loads(response.content)["html"]
        self.assertIn('>Sponsor name:</label>', html)
        self.assertNotIn('>Contributor name:</label>', html)

    def setUp(self):
        self.contributor = Contributor(
            pk=7, contributor_name="Oak & Co.", contributor_type="Sponsor", contact_name="Alex",
            phone="07700900123", email="alex@example.com", description="Full description",
            socials={"Website": "https://example.com"},
        )
        self.contributor.save = Mock()
        self.url = reverse("contributors:details", args=[7])
        self.history_lookup = patch("Contributors.views.details.ContributorHistory.objects.filter").start()
        self.confirmation_lookup = patch("Contributors.views.details.ContributorEvent.objects.filter").start()
        self.confirmation_lookup.return_value.select_related.return_value.order_by.return_value = []
        self.contribution_history = patch("Contributors.views.details.Contributions.objects.filter").start()
        self.contribution_history.return_value.select_related.return_value.order_by.return_value = []
        self.addCleanup(patch.stopall)
        self.history_lookup.return_value.select_related.return_value.order_by.return_value = []
        self.current_event = patch("Contributors.views.details.get_current_contribution_event", return_value=None).start()

    def request(self, method="get", data=None):
        request = getattr(RequestFactory(), method)(self.url, data or {})
        request.user = SimpleNamespace(is_authenticated=True, is_active=True, has_perm=lambda permission: True)
        return request

    def payload(self, **changes):
        values = {
            "contributor_name": "Oak & Co.", "contributor_type": "Sponsor", "contact_name": "Alex",
            "phone": "07700900123", "email": "alex@example.com", "description": "Full description",
            "socials": json.dumps({"Website": "https://example.com"}),
        }
        values.update(changes)
        return {f"details-{key}": value for key, value in values.items()}

    @patch("Contributors.views.details.get_object_or_404")
    def test_get_renders_every_model_field_and_escapes_values(self, lookup):
        lookup.return_value = self.contributor
        self.contributor.description = '<script>alert("unsafe")</script>'
        response = contributor_details(self.request(), pk=7)
        self.assertEqual(response.status_code, 200)
        html = json.loads(response.content)["html"]
        self.assertNotIn("Contributor ID", html)
        self.assertNotIn('name="details-contributor_type"', html)
        for field in ContributorDetailsForm.Meta.fields:
            self.assertIn(f'name="details-{field}"', html)
        self.assertIn("&lt;script&gt;", html)
        self.assertNotIn('<script>alert', html)
        self.assertIn('name="csrfmiddlewaretoken"', html)

    @patch("Contributors.views.details.transaction.atomic", return_value=nullcontext())
    @patch("Contributors.views.details.ContributorHistory.objects.create")
    @patch("Contributors.views.details.get_object_or_404")
    def test_save_updates_full_details_and_records_history(self, lookup, history, atomic):
        lookup.return_value = self.contributor
        request = self.request("post", self.payload(
            description="Revised description", socials='{"Instagram": "@oak"}', contributor_type="Donor",
        ))
        response = contributor_details(request, pk=7)
        self.assertEqual(response.status_code, 200)
        self.contributor.save.assert_called_once()
        self.assertEqual(self.contributor.description, "Revised description")
        self.assertEqual(self.contributor.socials, {"Instagram": "@oak"})
        self.assertEqual(self.contributor.contributor_type, "Sponsor")
        self.assertEqual(history.call_args.kwargs["event_category"], "Data")
        self.assertIs(history.call_args.kwargs["user"], request.user)
        self.assertIn("description", history.call_args.kwargs["details"])
        self.assertEqual(json.loads(response.content)["contributor"]["details_url"], self.url)

    @patch("Contributors.views.details.transaction.atomic", return_value=nullcontext())
    @patch("Contributors.views.details.ContributorHistory.objects.create")
    @patch("Contributors.views.details.get_object_or_404")
    def test_invalid_data_does_not_save(self, lookup, history, atomic):
        lookup.return_value = self.contributor
        response = contributor_details(self.request("post", self.payload(email="bad", socials="[]")), pk=7)
        self.assertEqual(response.status_code, 400)
        self.assertIn("email", json.loads(response.content)["errors"])
        self.assertIn("socials", json.loads(response.content)["errors"])
        self.contributor.save.assert_not_called()
        history.assert_not_called()

    @patch("Contributors.views.details.transaction.atomic", return_value=nullcontext())
    @patch("Contributors.views.details.ContributorHistory.objects.create")
    @patch("Contributors.views.details.get_object_or_404")
    def test_unchanged_form_does_not_create_history(self, lookup, history, atomic):
        lookup.return_value = self.contributor
        response = contributor_details(self.request("post", self.payload()), pk=7)
        self.assertEqual(response.status_code, 200)
        self.contributor.save.assert_not_called()
        history.assert_not_called()

    def test_invalid_icon_is_rejected(self):
        form = ContributorDetailsForm(
            self.payload(), {"details-icon": SimpleUploadedFile("icon.png", b"not an image")},
            instance=self.contributor, prefix="details",
        )
        self.assertFalse(form.is_valid())
        self.assertIn("icon", form.errors)

    def test_login_and_method_restrictions(self):
        request = self.request()
        request.user.is_authenticated = False
        self.assertEqual(contributor_details(request, pk=7).status_code, 302)
        request = RequestFactory().delete(self.url)
        request.user = SimpleNamespace(is_authenticated=True, is_active=True, has_perm=lambda permission: True)
        self.assertEqual(contributor_details(request, pk=7).status_code, 405)

    @patch("Contributors.views.details.get_object_or_404")
    def test_history_groups_confirmations_and_contributions_by_event(self, lookup):
        lookup.return_value = self.contributor
        old = SimpleNamespace(pk=1, event_date=date(2025, 6, 1))
        recent = SimpleNamespace(pk=2, event_date=date(2026, 6, 1))
        self.current_event.return_value = recent
        confirmations = self.confirmation_lookup.return_value.select_related.return_value
        confirmations.order_by.return_value = [
            SimpleNamespace(event=recent, status="Declined", timestamp=datetime(2026, 5, 2, tzinfo=timezone.utc),
                            user=SimpleNamespace(get_full_name=lambda: "Alex")),
            SimpleNamespace(event=recent, status="Confirmed", timestamp=datetime(2026, 5, 1, tzinfo=timezone.utc), user=None),
            SimpleNamespace(event=old, status="Confirmed", timestamp=datetime(2025, 5, 1, tzinfo=timezone.utc), user=None),
        ]
        self.contribution_history.return_value.select_related.return_value.order_by.return_value = [
            SimpleNamespace(event=old, cash=False, gift="Older <voucher>"),
            SimpleNamespace(event=recent, cash=True, gift="£50"),
            SimpleNamespace(event=None, cash=False, gift="Unassigned gift"),
        ]
        html = json.loads(contributor_details(self.request(), pk=7).content)["history_html"]
        self.history_lookup.assert_not_called()
        self.confirmation_lookup.assert_called_once_with(contributor=self.contributor)
        confirmations.order_by.assert_called_once_with("-timestamp", "-pk")
        self.assertLess(html.index("Declined"), html.index("Confirmed"))
        self.assertLess(html.index("£50"), html.index("Older &lt;voucher&gt;"))
        self.assertLess(html.index("Older &lt;voucher&gt;"), html.index("Unassigned gift"))
        self.assertIn("Recorded by Alex", html)
        self.assertIn("Cash:</strong> £50", html)
        self.assertNotIn("Data / Changed", html)

    @patch("Contributors.views.details.get_object_or_404")
    def test_history_refresh_returns_only_history_without_details_fields(self, lookup):
        lookup.return_value = self.contributor
        request = self.request(data={"history": "1"})
        data = json.loads(contributor_details(request, pk=7).content)
        self.assertIn("No confirmation or contribution history yet.", data["history_html"])
        self.assertNotIn("html", data)

    @patch("Contributors.views.contributions.Contributions.objects.filter")
    @patch("Contributors.views.details.get_object_or_404")
    def test_current_event_contributions_are_shown_in_details(self, lookup, contributions):
        contributions.return_value.select_related.return_value.order_by.return_value = []
        lookup.return_value = self.contributor
        event = self.current_event.return_value = "Current event"
        contributions.return_value.order_by.return_value = [
            SimpleNamespace(pk=1, gift="Prize voucher"), SimpleNamespace(pk=2, gift="Gift <basket>"),
        ]
        html = json.loads(contributor_details(self.request(), pk=7).content)["html"]
        contributions.assert_any_call(contributor=self.contributor, event=event)
        contributions.return_value.order_by.assert_called_once_with("pk")
        self.assertIn("Current event contributions", html)
        self.assertIn("Prize voucher", html)
        self.assertIn("Gift &lt;basket&gt;", html)
        self.assertIn('<p class="contribution-gift"><strong>Gift:</strong> Prize voucher', html)
        self.assertIn('value="Add contribution"', html)
        self.assertIn('aria-label="Delete contribution" title="Delete contribution"', html)
        self.assertIn('class="contribution-delete-icon"', html)
        self.assertNotIn('<span aria-hidden="true">×</span>', html)
        self.assertNotIn('>Delete contribution</button>', html)

    @patch("Contributors.views.contributions.Contributions.objects.filter")
    @patch("Contributors.views.details.get_object_or_404")
    def test_empty_current_event_still_offers_first_contribution(self, lookup, contributions):
        lookup.return_value = self.contributor
        event = SimpleNamespace(pk=23)
        self.current_event.return_value = event
        contributions.return_value.select_related.return_value.order_by.return_value = []
        contributions.return_value.order_by.return_value = []
        html = json.loads(contributor_details(self.request(), pk=7).content)["html"]
        self.assertIn("Current event contributions", html)
        self.assertIn("No contributions recorded for this event.", html)
        self.assertIn('value="Add contribution"', html)
        self.assertIn('data-event-id="23"', html)
        self.assertIn(f'data-contribution-url="{reverse("contributors:add_contribution", args=[7])}"', html)

    @patch("Contributors.views.contributions.Contributions.objects.filter")
    @patch("Contributors.views.details.get_object_or_404")
    def test_empty_contributions_respect_add_permission(self, lookup, contributions):
        lookup.return_value = self.contributor
        self.current_event.return_value = SimpleNamespace(pk=23)
        contributions.return_value.select_related.return_value.order_by.return_value = []
        contributions.return_value.order_by.return_value = []
        request = self.request()
        request.user.has_perm = lambda permission: permission != "Contributors.add_contributions"
        html = json.loads(contributor_details(request, pk=7).content)["html"]
        self.assertIn("No contributions recorded for this event.", html)
        self.assertNotIn('value="Add contribution"', html)

    @patch("Contributors.views.contributions.Contributions.objects.filter")
    @patch("Contributors.views.details.get_object_or_404")
    def test_no_current_event_hides_contributions(self, lookup, contributions):
        contributions.return_value.select_related.return_value.order_by.return_value = []
        lookup.return_value = self.contributor
        html = json.loads(contributor_details(self.request(), pk=7).content)["html"]
        self.assertNotIn({"contributor": self.contributor, "event": None}, [call.kwargs for call in contributions.call_args_list])
        self.assertNotIn("Current event contributions", html)

    def test_template_uses_display_flag_even_when_contributions_exist(self):
        context = {
            "contributor": self.contributor,
            "form": ContributorDetailsForm(instance=self.contributor, prefix="details"),
            "current_event": "Current event",
            "contributions": [SimpleNamespace(pk=1, gift="Prize voucher")],
            "show_contributions": False,
            "csrf_token": "test-token",
        }
        html = render_to_string("contributor_details_form.html", context)
        self.assertNotIn("Current event contributions", html)
        self.assertNotIn("Prize voucher", html)
        self.assertNotIn('value="Add contribution"', html)
        context["show_contributions"] = True
        self.assertIn("Prize voucher", render_to_string("contributor_details_form.html", context))

    @patch("Contributors.views.details.get_object_or_404")
    @patch("Contributors.views.details.contributions_context")
    def test_spreadsheet_can_disable_contributions_in_details(self, contributions, lookup):
        lookup.return_value = self.contributor
        request = self.request(data={"show_contributions": "0"})
        html = json.loads(contributor_details(request, pk=7).content)["html"]
        self.assertNotIn("Current event contributions", html)
        # History still needs the current event even when editing is disabled.
        self.current_event.assert_called_once_with()
        contributions.assert_not_called()
        self.assertNotIn({"contributor": self.contributor, "event": None}, [call.kwargs for call in contributions.call_args_list])

    @patch("Contributors.views.details.get_object_or_404")
    def test_socials_are_rendered_as_key_value_grid(self, lookup):
        lookup.return_value = self.contributor
        self.contributor.socials = {"Website": "https://example.com", "Note": '<script>unsafe</script>'}
        html = json.loads(contributor_details(self.request(), pk=7).content)["html"]
        self.assertIn('class="socials-grid"', html)
        self.assertIn('class="social-key" type="text" value="Website"', html)
        self.assertIn('class="social-value" type="text" value="https://example.com"', html)
        self.assertIn('&lt;script&gt;unsafe&lt;/script&gt;', html)
        self.assertNotIn('<textarea name="details-socials"', html)

    @patch("Contributors.views.details.get_object_or_404")
    def test_icon_shows_preview_and_edit_controls_without_path_text(self, lookup):
        lookup.return_value = self.contributor
        self.contributor.icon = "contributors/oak-logo.png"
        html = json.loads(contributor_details(self.request(), pk=7).content)["html"]
        self.assertIn('class="contributor-icon-preview"', html)
        self.assertIn(f'src="{self.contributor.icon.url}"', html)
        self.assertNotIn('href=', html)
        self.assertNotIn('>contributors/oak-logo.png<', html)
        self.assertIn('name="details-icon"', html)
        self.assertIn('name="details-icon-clear"', html)
        self.assertIn("Remove icon", html)
