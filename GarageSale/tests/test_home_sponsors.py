from types import SimpleNamespace
from unittest.mock import patch

from django.conf import settings
from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase, override_settings

from Contributors.models import Contributor
from GarageSale.views.general_views import home


class HomeSponsorTests(SimpleTestCase):
    @patch("GarageSale.views.general_views.NewsArticle.FrontPageOrder.all", return_value=[])
    def test_home_uses_current_event_confirmed_contributors(self, articles):
        request = RequestFactory().get("/")
        request.current_event = SimpleNamespace(pk=123)
        sponsors = home(request).context_data["sponsors"]
        self.assertEqual(sponsors.model, Contributor)
        sql, params = sponsors.query.sql_with_params()
        self.assertIn("Sponsor", params)
        self.assertIn("Confirmed", params)
        self.assertIn(123, params)
        self.assertIn("LIMIT 1", sql)

    @patch("GarageSale.views.general_views.NewsArticle.FrontPageOrder.all", return_value=[])
    @patch("GarageSale.views.general_views.get_current_contribution_event", return_value=None)
    def test_missing_event_shows_no_sponsors(self, event, articles):
        request = RequestFactory().get("/")
        request.current_event = None
        self.assertEqual(list(home(request).context_data["sponsors"]), [])

    @patch("GarageSale.templatetags.garage_sale_data.MOTD.get_current", return_value=None)
    def test_carousel_uses_contributor_icons_and_falls_back_to_names(self, motd):
        templates = [{
            "BACKEND": "django.template.backends.django.DjangoTemplates",
            "DIRS": [settings.BASE_DIR / "GarageSale" / "templates"],
            "OPTIONS": {
                "loaders": [("django.template.loaders.locmem.Loader", {
                    "_snap_slider_base.html": "{% block SnappableSections %}{% endblock %}",
                }), "django.template.loaders.filesystem.Loader"],
                "libraries": settings.TEMPLATES[0]["OPTIONS"]["libraries"],
            },
        }]
        sponsors = [Contributor(contributor_name="Oak & Co", icon="contributors/oak.png"),
                    Contributor(contributor_name="No logo")]
        with override_settings(TEMPLATES=templates):
            html = render_to_string("home.html", {"sponsors": sponsors})
        self.assertIn('alt="Oak &amp; Co"', html)
        self.assertIn(sponsors[0].icon.url, html)
        self.assertIn('<span class="sponsor-name">No logo</span>', html)
        self.assertIn("document.location.replace('/sponsors/')", html)
