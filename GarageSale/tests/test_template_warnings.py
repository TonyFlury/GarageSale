from datetime import date, timedelta
from types import SimpleNamespace

from django.test import RequestFactory, TestCase

from GarageSale.models import CommunicationTemplate, TemplateAttachment
from GarageSale.views.template_views import CommunicationTemplateCategories


class CommunicationTemplateWarningTests(TestCase):
    def setUp(self):
        self.template = self.create_template()

    def create_template(self, **overrides):
        values = {"category": "Sponsors", "sub_category": "Invite", "summary": "Invitation",
                  "subject": "Hello", "html_content": "<p>Hello</p>", "signature": "Team", "use_from": date(2026, 10, 12)}
        values.update(overrides)
        return CommunicationTemplate.objects.create(**values)

    def test_missing_named_attachment_and_wrong_category(self):
        TemplateAttachment.objects.create(template=self.template, template_name="Terms")
        self.create_template(category="Location", summary="Terms")
        warning = self.template.attachment_warnings()
        self.assertIn("Missing named attachment templates: Terms", warning)
        self.assertNotIn("become usable", warning)

    def test_late_named_attachment_and_inclusive_date_boundary(self):
        TemplateAttachment.objects.create(template=self.template, template_name="Terms")
        attachment = self.create_template(summary="Terms", use_from=self.template.use_from + timedelta(days=1))
        self.assertIn("become usable after this template: Terms", self.template.attachment_warnings())
        attachment.use_from = self.template.use_from
        attachment.save()
        self.assertEqual(self.template.attachment_warnings(), "")

    def test_same_summary_in_wrong_sub_category_does_not_match(self):
        TemplateAttachment.objects.create(template=self.template, template_name="Certificate")
        self.create_template(summary="Certificate", sub_category="Other")
        self.assertIn("Missing", self.template.attachment_warnings())
        self.create_template(summary="Certificate")
        self.assertEqual(self.template.attachment_warnings(), "")

    def test_older_version_satisfies_dependency_and_uploads_are_ignored(self):
        TemplateAttachment.objects.create(template=self.template, template_name="Terms")
        TemplateAttachment.objects.create(template=self.template, upload=True, template_name="Not a template")
        self.create_template(summary="Terms", use_from=self.template.use_from + timedelta(days=1))
        self.create_template(summary="Terms", use_from=self.template.use_from - timedelta(days=1))
        self.assertEqual(self.template.attachment_warnings(), "")

    def test_missing_and_late_dependencies_are_reported_together(self):
        TemplateAttachment.objects.create(template=self.template, template_name="Missing")
        TemplateAttachment.objects.create(template=self.template, template_name="Late")
        self.create_template(summary="Late", use_from=self.template.use_from + timedelta(days=1))
        warning = self.template.attachment_warnings()
        self.assertIn("Missing named attachment templates: Missing", warning)
        self.assertIn("become usable after this template: Late", warning)

    def test_list_marks_affected_rows_without_per_row_queries(self):
        TemplateAttachment.objects.create(template=self.template, template_name="Terms")
        healthy = self.create_template(sub_category="Thanks", summary="Thanks")
        request = RequestFactory().get("/", {"category": "Sponsors"})
        request.user = SimpleNamespace(is_authenticated=True, has_perms=lambda permissions: True)
        with self.assertNumQueries(3):
            response = CommunicationTemplateCategories.as_view()(request)
        rows = {row["pk"]: row for row in response.context_data["templates"]}
        self.assertIn("Missing", rows[self.template.pk]["attachment_warning"])
        self.assertEqual(rows[healthy.pk]["attachment_warning"], "")

    def test_list_recognises_certificate_in_matching_sub_category(self):
        self.template.sub_category = "confirmed"
        self.template.save()
        TemplateAttachment.objects.create(template=self.template, template_name="Thank you certificate")
        self.create_template(summary="Thank you certificate", sub_category="confirmed")
        request = RequestFactory().get("/", {"category": "Sponsors"})
        request.user = SimpleNamespace(is_authenticated=True, has_perms=lambda permissions: True)
        response = CommunicationTemplateCategories.as_view()(request)
        rows = {row["pk"]: row for row in response.context_data["templates"]}
        self.assertEqual(rows[self.template.pk]["attachment_warning"], "")

    def test_legacy_warning_fragment_escapes_attachment_names(self):
        TemplateAttachment.objects.create(template=self.template, template_name="<script>")
        html = self.template.warning_as_html_fragment()
        self.assertIn("&lt;script&gt;", html)
        self.assertNotIn("<script>", html)
