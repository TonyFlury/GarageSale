from types import SimpleNamespace
from unittest.mock import Mock, patch
import io
import zipfile

from django.test import RequestFactory, SimpleTestCase, override_settings

from Sponsors.views import SponsorSpreadsheetView


@override_settings(APPS_SETTINGS={"Sponsors": {"EmailTemplateCategory": "CustomSponsors"}})
class SponsorPDFTemplateTests(SimpleTestCase):
    def show_dialog(self, data=None, templates=None):
        request = RequestFactory().post("/sponsors/", data or {
            "selected_contributor": ["7", "8"], "selected_filters": "cash_donated",
        })
        view = SponsorSpreadsheetView()
        view.setup(request)
        with patch("Sponsors.views.CommunicationTemplate.current_active.filter", return_value=templates or []) as lookup:
            view.generate_pdf(request.POST)
        lookup.assert_called_once_with(category="CustomSponsors")
        return view

    def test_all_subcategories_are_listed_and_selection_is_preserved(self):
        templates = [SimpleNamespace(pk=i, summary=name, subject=name, sub_category=name) for i, name in
                     ((1, "Invite"), (2, "Confirmed"), (3, "Attachment"))]
        html = self.show_dialog(templates=templates).modal_html
        for template in templates:
            self.assertIn(f'<option value="{template.pk}">{template.summary}</option>', html)
        self.assertIn('name="selected_contributor" value="7"', html)
        self.assertIn('name="selected_contributor" value="8"', html)
        self.assertIn('name="selected_filters" value="cash_donated"', html)
        self.assertIn('name="toolbar_action" value="generate_pdf"', html)

    def test_valid_choice_downloads_all_pdfs_without_rerendering(self):
        template = SimpleNamespace(pk=1, summary="Sponsor letter", subject="Sponsor letter",
                                   render_template_as_pdf=Mock(side_effect=[b"%PDF-first", b"%PDF-second"]))
        sponsors = [SimpleNamespace(pk=7, contributor_name="Acme", email=""),
                    SimpleNamespace(pk=8, contributor_name="Acme", email="b@example.com")]
        contexts = [(sponsors[0], {"company_name": "Acme"}), (sponsors[1], {"company_name": "Acme"})]
        request = RequestFactory().post("/sponsors/", {
            "toolbar_action": "generate_pdf", "pdf_template_id": "1",
            "pdf_template_choice": "1", "selected_contributor": ["7", "8"],
        })
        view = SponsorSpreadsheetView()
        view.setup(request)
        with patch("Sponsors.views.CommunicationTemplate.current_active.filter", return_value=[template]), \
             patch.object(view, "_get_selected_email_sponsors", return_value=sponsors), \
             patch.object(view, "_sponsor_template_contexts", return_value=contexts), \
             patch.object(view, "get", side_effect=AssertionError("Download must not rerender")):
            response = view.post(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/zip")
        self.assertRegex(response["Content-Disposition"], r'Sponsor_letter \d{4}-\d{2}-\d{2} \d{2}-\d{2}-\d{2}\.zip')
        with zipfile.ZipFile(io.BytesIO(b"".join(response.streaming_content))) as archive:
            self.assertEqual(archive.namelist(), ["Acme.pdf", "Acme (2).pdf"])
            self.assertEqual(archive.read("Acme.pdf"), b"%PDF-first")
            self.assertEqual(archive.read("Acme (2).pdf"), b"%PDF-second")
        self.assertEqual(template.render_template_as_pdf.call_count, 2)
        response.close()

    def test_invalid_missing_or_multiple_choices_show_error(self):
        for ids in ([], ["999"], ["1", "2"]):
            with self.subTest(ids=ids):
                view = self.show_dialog({"pdf_template_id": ids, "pdf_template_choice": "1"})
                self.assertIsNone(view.selected_pdf_template)
                self.assertIn('role="alert"', view.modal_html)

    def test_empty_category_shows_message(self):
        self.assertIn("No PDF templates are currently available", self.show_dialog().modal_html)

    @override_settings(APPS_SETTINGS={"Sponsors": {"EmailFrom": "sponsors@example.com"}})
    def test_shared_context_includes_sponsors_without_email_and_is_fresh(self):
        request = RequestFactory().post("/sponsors/")
        request.current_event = None
        view = SponsorSpreadsheetView()
        view.setup(request)
        sponsors = [SimpleNamespace(pk=i, contributor_name=f"Sponsor {i}", contact_name=" Alex ",
                                   email="", previously_confirmed=True) for i in (7, 8)]
        with patch("Sponsors.views.get_current_contribution_event", return_value=None), \
             patch.object(view, "_cash_donations", return_value={7: "£50"}):
            contexts = list(view._sponsor_template_contexts(sponsors))
        first, second = contexts[0][1], contexts[1][1]
        self.assertIsNot(first, second)
        self.assertEqual(first["company_name"], "Sponsor 7")
        self.assertEqual(first["contact_name"], "Alex")
        self.assertEqual(first["attn"], "For Attn of :Alex")
        self.assertEqual(first["from"], "sponsors@example.com")
        self.assertEqual(first["donation"], "£50")
        self.assertNotIn("donation", second)
        self.assertTrue(first["previously_confirmed"])

    def test_filename_removes_path_separators_and_handles_empty_names(self):
        self.assertEqual(SponsorSpreadsheetView._pdf_filename("../Acme", "Sponsor"), "..Acme")
        self.assertEqual(SponsorSpreadsheetView._pdf_filename("", "Sponsor"), "Sponsor")
