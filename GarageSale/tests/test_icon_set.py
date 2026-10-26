from django.template.loader import render_to_string
from django.test import SimpleTestCase


class IconSetTests(SimpleTestCase):
    def test_icon_attributes_are_escaped(self):
        html = render_to_string("email/icon_set.html", {"icons": [
            {"url": 'https://example.com/logo.svg?a=1&b=2', "name": 'Charity "A" <team>'},
        ]})
        self.assertIn('a=1&amp;b=2', html)
        self.assertIn('alt="Charity &quot;A&quot; &lt;team&gt;"', html)

    def test_no_icons_produces_empty_fragment(self):
        self.assertEqual(render_to_string("email/icon_set.html", {"icons": []}).strip(), "")
