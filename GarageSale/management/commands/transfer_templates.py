"""Move communication templates and their uploaded attachments between installations."""
import base64
import binascii
import json
from pathlib import Path
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from GarageSale.models import CommunicationTemplate, TemplateAttachment


FIELDS = ("category", "sub_category", "summary", "subject", "html_content", "signature", "use_from")
KEY_FIELDS = ("category", "sub_category", "summary", "use_from")


class Command(BaseCommand):
    help = "Export/import portable JSON template bundles, including uploaded attachments and all selected versions."

    def add_arguments(self, parser):
        parser.add_argument("operation", choices=("export", "import"))
        parser.add_argument("bundle", type=Path)
        parser.add_argument("--category", action="append", help="Export this category; repeat for multiple categories. Default: all.")
        parser.add_argument("--dry-run", action="store_true", help="Validate and report an import without writing anything.")
        parser.add_argument("--replace", action="store_true", help="Replace conflicting versions with the same category, subcategory, summary and Use from date.")

    def handle(self, *args, **options):
        if options["operation"] == "export":
            if options["replace"] or options["dry_run"]:
                raise CommandError("--replace and --dry-run apply only to imports.")
            return self.export_bundle(options)
        if options["category"]:
            raise CommandError("Select categories during export, not import.")
        self.import_bundle(options)

    @staticmethod
    def _record(template):
        """Serialize logical values and file bytes, never database IDs or media paths."""
        fields = {name: getattr(template, name) for name in FIELDS}
        fields["use_from"] = template.use_from.isoformat()
        attachments = []
        for attachment in template.attachments.order_by("pk"):
            entry = {"upload": attachment.upload, "template_name": attachment.template_name}
            if attachment.upload:
                if not attachment.attached_file:
                    raise CommandError(f"Uploaded attachment has no file: {template.summary}.")
                try:
                    with attachment.attached_file.open("rb") as source:
                        entry.update(filename=Path(attachment.attached_file.name).name,
                                     content=base64.b64encode(source.read()).decode("ascii"))
                except OSError as error:
                    raise CommandError(f"Cannot read attachment for {template.summary}: {error}") from error
            attachments.append(entry)
        return {"fields": fields, "attachments": attachments}

    def export_bundle(self, options):
        queryset = CommunicationTemplate.objects.order_by("category", "summary", "use_from", "pk").prefetch_related("attachments")
        if options["category"]:
            queryset = queryset.filter(category__in=options["category"])
        records = [self._record(template) for template in queryset]
        if not records:
            raise CommandError("No templates match the selected categories.")

        # Export all versions in each selected category, so named attachment
        # templates travel with their parents even if their dates differ.
        bundle = {"format": "garagesale-templates", "version": 1, "templates": records}
        try:
            with options["bundle"].open("x", encoding="utf-8") as destination:
                json.dump(bundle, destination, ensure_ascii=False, indent=2)
        except OSError as error:
            raise CommandError(f"Cannot create bundle (existing files are not overwritten): {error}") from error
        self.stdout.write(self.style.SUCCESS(f"Exported {len(records)} template versions to {options['bundle']}."))

    @staticmethod
    def _read_bundle(path):
        """Validate every entry before writing database records or media files."""
        try:
            bundle = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(bundle, dict) or bundle.get("format") != "garagesale-templates" or bundle.get("version") != 1:
                raise ValueError("Unsupported template bundle format.")
            records = bundle["templates"]
            if not isinstance(records, list) or not records:
                raise ValueError("The bundle contains no templates.")
            seen = set()
            for record in records:
                fields, attachments = record["fields"], record["attachments"]
                if set(fields) != set(FIELDS) or not isinstance(attachments, list):
                    raise ValueError("Invalid fields or attachments.")
                template = CommunicationTemplate(**fields)
                template.full_clean(validate_unique=False, validate_constraints=False)
                key = tuple(getattr(template, name) for name in KEY_FIELDS)
                if key in seen:
                    raise ValueError("Multiple exported versions share category, subcategory, summary and Use from date.")
                seen.add(key)
                for entry in attachments:
                    if not isinstance(entry["upload"], bool) or not isinstance(entry["template_name"], str):
                        raise ValueError("Invalid attachment metadata.")
                    if len(entry["template_name"]) > 100:
                        raise ValueError("Attachment template name is too long.")
                    if entry["upload"]:
                        filename = entry["filename"]
                        if not isinstance(filename, str) or not filename or filename in (".", "..") or "/" in filename or "\\" in filename:
                            raise ValueError("Attachment filenames must not contain paths.")
                        if len(filename) + 22 > TemplateAttachment._meta.get_field("attached_file").max_length:
                            raise ValueError("Attachment filename is too long for destination storage.")
                        base64.b64decode(entry["content"], validate=True)
                    elif not entry["template_name"]:
                        raise ValueError("Named attachments require a template summary.")
            return records
        except (OSError, UnicodeError, ValueError, KeyError, TypeError, AttributeError, ValidationError, binascii.Error) as error:
            raise CommandError(f"Invalid template bundle: {error}") from error

    def import_bundle(self, options):
        records = self._read_bundle(options["bundle"])
        plan = []
        skipped = 0

        # Lock matching versions until the whole import succeeds. Conflicts
        # abort before files are written unless the operator requested replacement.
        with transaction.atomic():
            for record in records:
                key = {name: record["fields"][name] for name in KEY_FIELDS}
                matches = list(CommunicationTemplate.objects.select_for_update().filter(**key))
                if len(matches) > 1:
                    raise CommandError(f"Ambiguous destination version: {key}.")
                existing = matches[0] if matches else None
                if existing and self._record(existing) == record:
                    skipped += 1
                    continue
                if existing and not options["replace"]:
                    raise CommandError(f"Conflicting destination version: {key}. Review it or explicitly use --replace.")
                plan.append((existing, record))
            if options["dry_run"]:
                self.stdout.write(self.style.SUCCESS(f"Dry run: {len(plan)} versions to import; {skipped} identical versions skipped. No changes made."))
                return

            # Storage does not participate in database transactions. Track only
            # newly saved files and remove them if any later import write fails.
            saved_files = []
            try:
                for existing, record in plan:
                    template = existing or CommunicationTemplate()
                    for name, value in record["fields"].items():
                        setattr(template, name, template._meta.get_field(name).to_python(value))
                    template.save()
                    template.attachments.all().delete()
                    for entry in record["attachments"]:
                        attachment = TemplateAttachment(template=template, upload=entry["upload"], template_name=entry["template_name"])
                        if entry["upload"]:

                            # Isolate storage paths while preserving the original
                            # basename: storage collision suffixes would otherwise
                            # change filenames and break identical-import checks.
                            filename = f"transfer/{uuid4().hex[:12]}/{entry['filename']}"
                            field = attachment._meta.get_field("attached_file")
                            attachment.attached_file.name = field.storage.save(
                                filename, ContentFile(base64.b64decode(entry["content"])), max_length=field.max_length,
                            )
                            saved_files.append((attachment.attached_file.storage, attachment.attached_file.name))
                        attachment.save()
            except Exception:
                for storage, name in saved_files:
                    storage.delete(name)
                raise
        self.stdout.write(self.style.SUCCESS(f"Imported {len(plan)} template versions; {skipped} identical versions skipped."))
