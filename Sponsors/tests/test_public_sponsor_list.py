import json
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from django.conf import settings
from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.urls import reverse

from Contributors.models import Contributor
from Sponsors.templatetags.social_media import social_media_link
from Sponsors.views import sponsor_list
from Sponsors.public_sponsors import confirmed_sponsors_for_event, sponsor_wall_for_event


class PublicSponsorListTests(SimpleTestCase):
    def request(self, event=None):
        request = RequestFactory().get(reverse("sponsors:sponsor_list"))
        request.current_event = event
        return request

    def test_query_uses_latest_current_event_confirmation_even_for_past_events(self):
        queryset = confirmed_sponsors_for_event(SimpleNamespace(pk=123, event_date=date(2025, 6, 1)))
        sql, params = queryset.query.sql_with_params()
        self.assertEqual(queryset.model, Contributor)
        self.assertIn("Sponsor", params)
        self.assertIn("Confirmed", params)
        self.assertIn(123, params)
        self.assertIn("LIMIT 1", sql)
        self.assertIn('"timestamp" DESC', sql)
        self.assertEqual(queryset.query.order_by, ("contributor_name", "pk"))

    @patch("Sponsors.views.get_current_contribution_event", return_value=None)
    def test_missing_event_has_empty_list(self, event):
        self.assertEqual(list(sponsor_list(self.request()).context_data["sponsors"]), [])

    @patch("Sponsors.views.get_current_contribution_event")
    def test_request_without_event_uses_current_event_fallback(self, event):
        event.return_value = SimpleNamespace(pk=456)
        with patch("Sponsors.views.sponsor_wall_for_event", return_value=[]) as wall:
            sponsor_list(self.request())
        wall.assert_called_once_with(event.return_value)

    def test_social_links_use_dictionary_or_migrated_json_and_escape_names(self):
        for socials in ({"Website": "https://example.com/"}, json.dumps({"website": "https://example.com/"})):
            html = social_media_link(SimpleNamespace(contributor_name="Oak & Co", socials=socials), "website")
            self.assertIn('href="https://example.com/"', html)
            self.assertIn("Oak &amp; Co", html)
        for socials in (None, {}, {"website": "javascript:alert(1)"}, {"website": None}):
            self.assertEqual(social_media_link(SimpleNamespace(socials=socials), "website"), "")

    def test_single_wall_card_preserves_details_and_handles_missing_logos(self):
        templates = [{
            "BACKEND": "django.template.backends.django.DjangoTemplates",
            "DIRS": [settings.BASE_DIR / "Sponsors" / "templates"],
            "OPTIONS": {
                "loaders": [("django.template.loaders.locmem.Loader", {
                    "_snap_slider_base.html": "{% block SnappableSections %}{% endblock %}",
                }), "django.template.loaders.filesystem.Loader"],
                "libraries": settings.TEMPLATES[0]["OPTIONS"]["libraries"],
            },
        }]
        contributor = Contributor(pk=7, contributor_type="Sponsor", contributor_name="Oak & Co",
                                  icon="contributors/oak.png", description="A <gift>",
                                  socials={"website": "https://example.com/"})
        with override_settings(TEMPLATES=templates):
            html = render_to_string("view_sponsors.html", {"sponsors": [contributor], "socials": ["website"]})
            self.assertIn("Oak &amp; Co", html)
            self.assertIn(contributor.icon.url, html)
            self.assertIn("A &lt;gift&gt;", html)
            self.assertIn('href="https://example.com/"', html)
            self.assertNotIn('class="email"', html)
            self.assertNotIn('class="phone"', html)
            self.assertEqual(html.count('class="card sponsor-wall-card"'), 1)
            self.assertIn('id="sponsor-logo-wall"', html)
            self.assertIn('aria-haspopup="dialog"', html)
            self.assertNotIn("Reshuffle", html)
            contributor.icon = ""
            html = render_to_string("view_sponsors.html", {"sponsors": [contributor]})
            self.assertNotIn('class="logo"', html)
            self.assertIn('class="sponsor-wall-name">Oak &amp; Co</span>', html)

    @patch("Sponsors.public_sponsors.Contributions.objects.filter")
    @patch("Sponsors.public_sponsors.confirmed_sponsors_for_event")
    def test_headliners_use_valid_event_cash_totals_without_exposing_amounts(self, sponsors, contributions):
        sponsors.return_value = [Contributor(pk=i, contributor_name=f"Sponsor {i}") for i in range(1, 7)]
        contributions.return_value.values_list.return_value = [
            (1, "£50"), (1, "£100"), (2, "200"), (3, "£300"), (4, "£400"),
            (5, "1"), (6, "NaN"), (6, "-1000"), (6, "not cash"),
        ]
        event = SimpleNamespace(pk=123)
        wall = sponsor_wall_for_event(event)
        self.assertEqual([s.pk for s in wall if s.wall_headliner], [1, 2, 3, 4])
        contributions.assert_called_once_with(contributor_id__in=[1, 2, 3, 4, 5, 6], event_id=123, cash=True)
        self.assertFalse(hasattr(wall[0], "cash_total"))

    @patch("Sponsors.public_sponsors.Contributions.objects.filter")
    @patch("Sponsors.public_sponsors.confirmed_sponsors_for_event")
    def test_non_cash_sponsors_are_retained_without_forced_headliners(self, sponsors, contributions):
        sponsors.return_value = [Contributor(pk=1, contributor_name="Gift donor")]
        contributions.return_value.values_list.return_value = []
        wall = sponsor_wall_for_event(SimpleNamespace(pk=123))
        self.assertEqual(len(wall), 1)
        self.assertFalse(wall[0].wall_headliner)
