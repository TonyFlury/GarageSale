from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase
from django.template import Context, Engine
from django.urls import reverse

from Contributors.views.contact_history import ContactHistoryForm, add_contact_history


class ContactHistoryTests(SimpleTestCase):
    def test_rendered_rows_have_icon_buttons_except_the_new_row(self):
        class Rows(HTMLParser):
            def __init__(self):
                super().__init__()
                self.rows = []
                self.row = None

            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                if tag == "tr":
                    self.row = {"attrs": attrs, "buttons": [], "images": []}
                    self.rows.append(self.row)
                elif self.row is not None and tag == "button":
                    self.row["buttons"].append(attrs)
                elif self.row is not None and tag == "img":
                    self.row["images"].append(attrs)

            def handle_endtag(self, tag):
                if tag == "tr":
                    self.row = None

        engine = Engine(
            libraries={"static": "django.templatetags.static"},
            loaders=[
                ("django.template.loaders.locmem.Loader", {
                    "team_pages_base.html": "{% block SnappableSections %}{% endblock %}",
                }),
                ("django.template.loaders.filesystem.Loader", [
                    str(Path(__file__).resolve().parents[1] / "templates"),
                ]),
            ],
        )
        html = engine.get_template("contributor_spreadsheet.html").render(Context({
            "can_add": True,
            "contributors": [SimpleNamespace(
                can_edit=True, can_contact=True, pk=7, contributor_name="Oak & Co.",
                current_event_contributions=[SimpleNamespace(gift="Prize voucher"),
                                             SimpleNamespace(gift="Gift <basket>"),
                                             SimpleNamespace(gift=None)],
            )],
            "csrf_token": "test-token",
        }))
        parsed = Rows()
        parsed.feed(html)
        existing = next(row for row in parsed.rows if row["attrs"].get("data-contributor-id") == "7")
        button = next(button for button in existing["buttons"] if button.get("class") == "add-contact-history")
        self.assertEqual(button["type"], "button")
        self.assertEqual(button["data-contact-history-url"], reverse("contributors:contact_history", args=[7]))
        self.assertEqual(button["aria-label"], "Record contact with Oak & Co.")
        self.assertEqual(button["aria-controls"], "contact-history-dialog")
        self.assertTrue(any("contact-us-svgrepo-com.svg" in img["src"] for img in existing["images"]))
        new_row = next(row for row in parsed.rows if row["attrs"].get("data-is-new") == "true")
        self.assertEqual(new_row["buttons"], [])
        self.assertIn('name="note" rows="3" maxlength="1000" required', html)
        self.assertIn('name="date" type="date" required', html)
        self.assertIn('id="contact-history-save" type="submit" value="Save"', html)
        self.assertNotIn("Current event gift", html)
        self.assertNotIn("Prize voucher", html)
        self.assertNotIn("Gift &lt;basket&gt;", html)

    def test_note_and_date_validation(self):
        for payload in (
            {"note": "  ", "date": "2026-10-10"},
            {"note": "x" * 1001, "date": "2026-10-10"},
            {"note": "Called", "date": "2026-02-30"},
            {"note": "Called", "date": ""},
        ):
            with self.subTest(payload=payload):
                self.assertFalse(ContactHistoryForm(payload).is_valid())

    @patch("Contributors.views.contact_history.ContributorHistory.objects.create")
    @patch("Contributors.views.contact_history.get_object_or_404")
    def test_saves_contact_comment_with_selected_date_and_user(self, lookup, create):
        lookup.return_value.contributor_type = "Sponsor"
        contributor = lookup.return_value
        create.return_value.pk = 42
        request = RequestFactory().post(reverse("contributors:contact_history", args=[7]), {
            "note": "  Called to discuss sponsorship  ", "date": "2026-10-09",
        })
        request.user = SimpleNamespace(is_authenticated=True, is_active=True, has_perm=lambda permission: True)
        response = add_contact_history(request, pk=7)
        self.assertEqual(response.status_code, 201)
        values = create.call_args.kwargs
        self.assertEqual(values["contributor"], contributor)
        self.assertEqual(values["event_category"], "Contact")
        self.assertEqual(values["event_type"], "Comment")
        self.assertEqual(values["details"], "Called to discuss sponsorship")
        self.assertEqual(values["timestamp"].date(), date(2026, 10, 9))
        self.assertIsNotNone(values["timestamp"].tzinfo)
        self.assertIs(values["user"], request.user)

    @patch("Contributors.views.contact_history.ContributorHistory.objects.create")
    @patch("Contributors.views.contact_history.get_object_or_404")
    def test_invalid_note_does_not_save(self, lookup, create):
        lookup.return_value.contributor_type = "Sponsor"
        request = RequestFactory().post("/", {"note": "", "date": "2026-10-10"})
        request.user = SimpleNamespace(is_authenticated=True, is_active=True, has_perm=lambda permission: True)
        self.assertEqual(add_contact_history(request, pk=7).status_code, 400)
        create.assert_not_called()

    def test_requires_login_and_post(self):
        request = RequestFactory().get("/")
        request.user = SimpleNamespace(is_authenticated=False)
        self.assertEqual(add_contact_history(request, pk=7).status_code, 302)
        request.user = SimpleNamespace(is_authenticated=True, is_active=True, has_perm=lambda permission: True)
        self.assertEqual(add_contact_history(request, pk=7).status_code, 405)
