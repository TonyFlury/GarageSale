from datetime import date
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase, override_settings

from GarageSale.models import CommunicationTemplate, TemplateAttachment
from GarageSale.views.template_views import CommunicationTemplateEdit


class CommunicationTemplateAttachmentTests(TestCase):
    def setUp(self):
        self.template = CommunicationTemplate.objects.create(
            category="Sponsors", sub_category="Invite", summary="Invitation", subject="Hello",
            html_content="<p>Hello</p>", signature="Team", use_from=date(2026, 10, 12),
        )
        storage = TemporaryDirectory()
        self.addCleanup(storage.cleanup)
        override = override_settings(MEDIA_ROOT=storage.name)
        override.enable()
        self.addCleanup(override.disable)

    def data(self, **extra):
        data = {"category": "Sponsors", "sub_category": "Invite", "summary": "Updated invitation",
                "subject": "Hello", "html_content": "<p>Hello</p>", "signature": "Team", "use_from": "2026-10-12",
                "attachments-TOTAL_FORMS": "1", "attachments-INITIAL_FORMS": "0"}
        data.update(extra)
        return data

    def submit(self, data):
        request = RequestFactory().post("/", data)
        request.user = SimpleNamespace(is_authenticated=True, is_active=True, has_perm=lambda permission: True, has_perms=lambda permissions: True)
        return CommunicationTemplateEdit.as_view()(request, pk=self.template.pk)

    def test_add_named_attachment(self):
        response = self.submit(self.data(**{"attachments-0-template_name": "Terms"}))
        self.assertEqual(response.status_code, 302)
        attachment = self.template.attachments.get()
        self.assertFalse(attachment.upload)
        self.assertEqual(attachment.template_name, "Terms")
        self.assertFalse(attachment.attached_file)

    def test_upload_file_does_not_require_template_name(self):
        response = self.submit(self.data(**{
            "attachments-0-upload": "on", "attachments-0-attached_file": SimpleUploadedFile("info.txt", b"Information"),
        }))
        self.assertEqual(response.status_code, 302)
        attachment = self.template.attachments.get()
        self.assertTrue(attachment.upload)
        self.assertEqual(attachment.template_name, "")
        self.assertIn("template_attachments/Sponsors/Invite/2026-10-12/info", attachment.attached_file.name)
        with attachment.attached_file.open("rb") as uploaded:
            self.assertEqual(uploaded.read(), b"Information")

    def test_each_mode_requires_its_own_value_without_saving_template_changes(self):
        for extra, field in (({}, "template_name"), ({"attachments-0-upload": "on"}, "attached_file")):
            response = self.submit(self.data(**extra))
            self.assertEqual(response.status_code, 200)
            self.assertIn(field, response.context_data["attachments"].forms[0].errors)
            self.template.refresh_from_db()
            self.assertEqual(self.template.summary, "Invitation")
            self.assertEqual(self.template.attachments.count(), 0)

    def test_existing_file_is_retained_when_no_new_file_is_uploaded(self):
        attachment = TemplateAttachment.objects.create(template=self.template, upload=True, attached_file="existing/info.pdf")
        response = self.submit(self.data(**{
            "attachments-INITIAL_FORMS": "1", "attachments-0-id": str(attachment.pk), "attachments-0-upload": "on",
        }))
        self.assertEqual(response.status_code, 302)
        attachment.refresh_from_db()
        self.assertEqual(attachment.attached_file.name, "existing/info.pdf")

    def test_switch_uploaded_attachment_to_named_template(self):
        attachment = TemplateAttachment.objects.create(template=self.template, upload=True, attached_file="existing/info.pdf")
        response = self.submit(self.data(**{
            "attachments-INITIAL_FORMS": "1", "attachments-0-id": str(attachment.pk), "attachments-0-template_name": "Terms",
        }))
        self.assertEqual(response.status_code, 302)
        attachment.refresh_from_db()
        self.assertFalse(attachment.upload)
        self.assertEqual(attachment.template_name, "Terms")
        self.assertFalse(attachment.attached_file)

    def test_remove_attachment_even_when_its_fields_are_empty(self):
        attachment = TemplateAttachment.objects.create(template=self.template, template_name="Terms")
        response = self.submit(self.data(**{
            "attachments-INITIAL_FORMS": "1", "attachments-0-id": str(attachment.pk), "attachments-0-DELETE": "on",
        }))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(TemplateAttachment.objects.filter(pk=attachment.pk).exists())

    def test_multiple_attachments_and_missing_management_form(self):
        response = self.submit(self.data(**{
            "attachments-TOTAL_FORMS": "2", "attachments-0-template_name": "Terms", "attachments-1-template_name": "Map",
        }))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(set(self.template.attachments.values_list("template_name", flat=True)), {"Terms", "Map"})
        data = self.data()
        del data["attachments-TOTAL_FORMS"]
        response = self.submit(data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context_data["attachments"].non_form_errors())
