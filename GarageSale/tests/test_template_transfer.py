"""Portable template bundles must preserve content without depending on source IDs."""
import json
from datetime import date
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from GarageSale.models import CommunicationTemplate, TemplateAttachment


class TemplateTransferTests(TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.bundle = Path(self.directory.name) / "templates.json"
        settings = override_settings(MEDIA_ROOT=self.directory.name)
        settings.enable()
        self.addCleanup(settings.disable)
        self.template = CommunicationTemplate.objects.create(
            category="Sponsors", sub_category="Invite", summary="Letter", subject="Hello {{ contact_name }}",
            html_content="<p>Hello</p>", signature="Team", use_from=date(2026, 1, 1),
        )
        TemplateAttachment.objects.create(template=self.template, template_name="Terms")
        attachment = TemplateAttachment(template=self.template, upload=True, template_name="")
        attachment.attached_file.save("information.pdf", ContentFile(b"%PDF-demo"))

    def command(self, operation, *args):
        call_command("transfer_templates", operation, str(self.bundle), *args, stdout=StringIO())

    def test_roundtrip_preserves_content_attachments_and_is_repeatable(self):
        self.command("export", "--category", "Sponsors")
        old_pk = self.template.pk
        CommunicationTemplate.objects.all().delete()
        self.command("import")
        template = CommunicationTemplate.objects.get()
        self.assertNotEqual(template.pk, old_pk)
        self.assertEqual(template.subject, "Hello {{ contact_name }}")
        self.assertEqual(template.attachments.get(upload=False).template_name, "Terms")
        with template.attachments.get(upload=True).attached_file.open("rb") as source:
            self.assertEqual(source.read(), b"%PDF-demo")
        self.command("import")
        self.assertEqual(CommunicationTemplate.objects.count(), 1)
        self.assertEqual(TemplateAttachment.objects.count(), 2)

    def test_conflict_aborts_and_replace_is_explicit(self):
        self.command("export")
        self.template.subject = "Edited on trial"
        self.template.save()
        with self.assertRaisesMessage(CommandError, "Conflicting"):
            self.command("import")
        self.template.refresh_from_db()
        self.assertEqual(self.template.subject, "Edited on trial")
        self.command("import", "--replace", "--dry-run")
        self.template.refresh_from_db()
        self.assertEqual(self.template.subject, "Edited on trial")
        self.command("import", "--replace")
        self.template.refresh_from_db()
        self.assertEqual(self.template.subject, "Hello {{ contact_name }}")

    def test_dry_run_creates_nothing(self):
        self.command("export")
        CommunicationTemplate.objects.all().delete()
        files = set(Path(self.directory.name).rglob("*"))
        self.command("import", "--dry-run")
        self.assertFalse(CommunicationTemplate.objects.exists())
        self.assertEqual(set(Path(self.directory.name).rglob("*")), files)

    def test_path_traversal_is_rejected_before_writes(self):
        self.command("export")
        bundle = json.loads(self.bundle.read_text())
        bundle["templates"][0]["attachments"][1]["filename"] = "../outside.pdf"
        self.bundle.write_text(json.dumps(bundle))
        with self.assertRaisesMessage(CommandError, "filenames must not contain paths"):
            self.command("import")
        self.assertEqual(CommunicationTemplate.objects.count(), 1)

    def test_failed_import_rolls_back_records_and_new_files(self):
        self.command("export")
        CommunicationTemplate.objects.all().delete()
        files = set(Path(self.directory.name).rglob("*.pdf"))
        original_save = TemplateAttachment.save

        def fail_after_file_save(attachment, *args, **kwargs):
            if attachment.upload:
                raise RuntimeError("Failed write")
            return original_save(attachment, *args, **kwargs)

        with patch.object(TemplateAttachment, "save", autospec=True, side_effect=fail_after_file_save):
            with self.assertRaises(RuntimeError):
                self.command("import")
        self.assertFalse(CommunicationTemplate.objects.exists())
        self.assertEqual(set(Path(self.directory.name).rglob("*.pdf")), files)
