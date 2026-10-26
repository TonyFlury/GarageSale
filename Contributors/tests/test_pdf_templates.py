"""Verify PDF downloads work directly on the shared spreadsheet base class."""
import io
import zipfile
from unittest.mock import patch

from django.test import RequestFactory, TestCase
from types import SimpleNamespace
from django.utils import timezone

from Contributors.models import Contributor
from Contributors.views.general_views import ContributorSpreadsheetView
from GarageSale.models import CommunicationTemplate


class SharedSpreadsheetPDFTests(TestCase):
    def setUp(self):
        self.contributor = Contributor.objects.create(
            contributor_type="Sponsor", contributor_name="Example company", contact_name="Alex", email="",
        )
        self.foreign = Contributor.objects.create(contributor_type="Other", contributor_name="Other")
        self.template = CommunicationTemplate.objects.create(
            category="Example", summary="Letter", subject="Letter", html_content="{{ contributor_name }}",
            use_from=timezone.localdate(),
        )

    def view(self, **data):
        request = RequestFactory().post("/example/", {
            "toolbar_action": "generate_pdf", "selected_contributor": [str(self.contributor.pk)], **data,
        })
        request.user = SimpleNamespace(is_authenticated=True, is_active=True, has_perm=lambda permission: True)
        request.current_event = None
        view = ContributorSpreadsheetView(
            contributor_type="Sponsor", pdf_template_category="Example",
            extra_toolbar_actions=(ContributorSpreadsheetView.pdf_toolbar_action,),
        )
        view.setup(request)
        return view

    def test_base_download_has_personalisation_without_subclass_or_email(self):
        view = self.view(pdf_template_id=str(self.template.pk))
        with patch("Contributors.views.general_views.get_current_contribution_event", return_value=None), \
             patch.object(CommunicationTemplate, "render_template_as_pdf", return_value=b"%PDF-base") as render:
            response = view.post(view.request)
        context = render.call_args.args[1]
        self.assertEqual(context["contributor_name"], "Example company")
        self.assertEqual(context["contact_name"], "Alex")
        with zipfile.ZipFile(io.BytesIO(b"".join(response.streaming_content))) as archive:
            self.assertEqual(archive.read("Example_company.pdf"), b"%PDF-base")
        response.file_to_stream.close()

    def test_invalid_or_partial_selection_never_produces_archive(self):
        for ids in (["bad"], [str(self.contributor.pk), str(self.foreign.pk)],
                    [str(self.contributor.pk), "999999"]):
            with self.subTest(ids=ids):
                view = self.view(pdf_template_id=str(self.template.pk), selected_contributor=ids)
                with patch.object(CommunicationTemplate, "render_template_as_pdf") as render:
                    self.assertIsNone(view.generate_pdf(view.request.POST))
                    render.assert_not_called()
                self.assertIn('role="alert"', view.modal_html)

    def test_template_category_is_required_and_foreign_templates_are_rejected(self):
        view = self.view(pdf_template_id=str(self.template.pk))
        view.pdf_template_category = "Other"
        self.assertIsNone(view.generate_pdf(view.request.POST))
        self.assertIn("no longer available", view.modal_html)
        view.pdf_template_category = None
        self.assertEqual(view.get_pdf_templates(), [])
