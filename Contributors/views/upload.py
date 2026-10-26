import csv
import io
import json
from datetime import date, datetime, time
from typing import TypedDict

from django.http import HttpResponseBadRequest
from django.db import transaction
from django.shortcuts import redirect, render
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from GarageSale.access_policy import contributor_types, require_contributor
from django.utils import timezone

from Contributors.models import Contributor, ContributorHistory


class ImportChanges(TypedDict):
    """Model instances prepared for saving after confirmation."""

    new_instances: list[Contributor]
    modified_instances: list[Contributor]
    new_history_instances: list[ContributorHistory]
    duplicate_history_count: int


class ImportReviewContext(ImportChanges):
    """Prepared instances and serialized form values used by the review page."""

    csv_path: str
    csv_data_json: str
    column_mapping_json: str
    contributor_type: str | None


class UploadCSV(LoginRequiredMixin, View):
    """Handle file selection, column matching, and action review at one URL."""

    CSV_FIELD_NAMES = ("contributor_name", "contact_name", "phone", "email", "description", "contributor_type")
    CSV_FIELDS = set(CSV_FIELD_NAMES)

    # History columns are import instructions, never attributes assigned to Contributor.
    HISTORY_FIELDS = {"contact_history", "contact_date"}

    def get(self, request, *args, **kwargs):
        """Render the initial page or download using the configured standard fields."""
        kinds = contributor_types(request.user, "import")
        if not kinds:
            raise PermissionDenied("You do not have permission to import contributors.")
        selected = self._contributor_type(request)
        return render(request, "upload/upload.html", {
            "contributor_types": kinds, "contributor_type": selected,
            "contributor_label": "Market Trader" if selected == "Marketer" else selected,
        })

    @staticmethod
    def _contributor_type(request):
        """Keep the originating spreadsheet's type throughout the import."""
        selected = request.GET.get("contributor_type")
        if selected:
            if selected not in contributor_types(request.user, "import"):
                raise PermissionDenied("You do not have permission to import these contributors.")
            posted = request.POST.get("contributor_type")
            if posted and posted != selected:
                raise PermissionDenied("The import must use the originating spreadsheet's contributor type.")
        return selected or request.POST.get("contributor_type")

    def post(self, request, *args, **kwargs):
        """Dispatch the submitted stage or action through the permitted workflow."""

        if not contributor_types(request.user, "import"):
            raise PermissionDenied("You do not have permission to import contributors.")
        self._contributor_type(request)

        # Only explicit workflow stages may advance a potentially destructive import.
        match request.POST.get("stage"):
            case "select_file":
                return self._csv_uploaded(request)
            case "match_columns":
                return self._columns_matched(request)
            case "review_changes":
                return self._actions_reviewed(request)
            case _:
                return HttpResponseBadRequest("Missing or invalid upload stage.")

    def _csv_uploaded(self, request):
        """Decode the upload before presenting safe column-matching data."""

        # Return user-correctable file problems without advancing the import stage.
        try:
            csv_path, csv_data = self._uploaded_text(request)
            columns, rows = self._csv_rows(csv_data)
        except ValueError as error:
            return HttpResponseBadRequest(str(error))
        return render(request, "upload/column_matching.html", {
            "csv_path": csv_path, "csv_data": rows, "possible_matches": self._match_names(columns),
            "contributor_type": self._contributor_type(request),
        })

    @staticmethod
    def _uploaded_text(request):
        """Accept browser-posted text or an uploaded UTF-8 CSV file."""
        csv_path, csv_data = request.POST.get("csv_path"), request.POST.get("csv_data")
        uploaded_file = request.FILES.get("csv_file")

        # Uploaded bytes take precedence over any earlier form copy of the CSV.
        if uploaded_file is not None:
            csv_path = csv_path or uploaded_file.name

            # Uploaded bytes need explicit decoding; arbitrary encodings would corrupt imported names.
            try:
                csv_data = uploaded_file.read().decode("utf-8-sig")
            except UnicodeDecodeError as error:
                raise ValueError("CSV file must use UTF-8 encoding.") from error

        # A filename identifies the review while the data supplies the proposed changes.
        if not csv_path or not csv_data:
            raise ValueError("Missing CSV file path or data.")
        return csv_path, csv_data

    @staticmethod
    def _csv_rows(csv_data):
        """Reject broken CSV syntax and empty imports before matching columns."""

        # Strict parsing catches malformed quoting instead of importing truncated values.
        try:
            reader = csv.DictReader(io.StringIO(csv_data.lstrip("\ufeff")), strict=True)
            columns, rows = reader.fieldnames, list(reader)
        except csv.Error as error:
            raise ValueError("Invalid CSV data.") from error

        # Matching needs both named columns and at least one example contributor.
        if not columns or not rows:
            raise ValueError("CSV must contain headers and at least one data row.")
        return columns, rows

    @staticmethod
    def _match_names(columns):
        """Return a mapping from CSV column names to model field names."""

        # TODO: Match CSV column names to Contributor fields.
        return {}

    @staticmethod
    def _validate_csv_data(rows, mapping, fields):
        """Validate the untrusted review payload before constructing model objects."""

        # Shape validation must precede field access on client-supplied JSON.
        if not UploadCSV._valid_import_shape(rows, mapping, fields):
            return "Invalid CSV data or column mapping."
        mapped_fields = [field for field in mapping.values() if field in fields | UploadCSV.HISTORY_FIELDS]

        # Contributor name is the identity key; duplicate destinations would discard data.
        if "contributor_name" not in mapped_fields or len(mapped_fields) != len(set(mapped_fields)):
            return "Map contributor name and select each model field only once."
        name_column = next(column for column, field in mapping.items() if field == "contributor_name")
        return UploadCSV._validate_import_values(rows, mapping, name_column)

    @staticmethod
    def _valid_import_shape(rows, mapping, fields):
        """Limit review JSON to string-valued rows and supported destinations."""

        # Empty and non-list payloads cannot supply a meaningful import review.
        if not isinstance(rows, list) or not rows:
            return False

        # Checking each row protects later string operations from malformed JSON values.
        for row in rows:

            # Later validation assumes string-valued cells and named columns.
            if not isinstance(row, dict) or any(not isinstance(key, str) or not isinstance(value, str)
                                                for key, value in row.items()):
                return False

        # Destination keys are an allowlist rather than arbitrary model attributes.
        if not isinstance(mapping, dict):
            return False
        allowed = fields | {"", "__ignore__", "__socials__"} | UploadCSV.HISTORY_FIELDS
        return all(isinstance(column, str) and isinstance(field, str) and field in allowed
                   for column, field in mapping.items())

    @staticmethod
    def _validate_import_values(rows, mapping, name_column):
        """Check identities and note lengths before building the review objects."""

        # Every row needs an identity even when its only change is a contact note.
        for row_number, row in enumerate(rows, start=2):

            # Every proposal needs a usable name for exact-match identity resolution.
            if not row.get(name_column, "").strip():
                return "Each CSV row must have a contributor name."

            # One cell is one complete note, including embedded line breaks. Never
            # interpret prose or a date inside the note as a separate contact.
            comment = UploadCSV._normalise_comment(UploadCSV._mapped_value(row, mapping, "contact_history"))
            contact_date = UploadCSV._mapped_value(row, mapping, "contact_date").strip()
            if len(comment) > 1000:
                return "Contact History comments must be 1000 characters or fewer."

            # Blank contact columns permit ordinary contributor-only updates. A
            # partial contact is rejected rather than silently dated as today.
            if bool(comment) != bool(contact_date):
                return f"CSV row {row_number}: Contact History and Contact date must both be supplied, or both left blank."
            if contact_date:
                try:
                    UploadCSV._contact_day(contact_date)
                except ValueError:
                    return f"CSV row {row_number}: Contact date must be a valid date in YYYY-MM-DD format."
        return None

    @staticmethod
    def _mapped_value(row, mapping, destination):
        """Read an optional import field regardless of the CSV's column heading."""
        column = next((column for column, field in mapping.items() if field == destination), None)
        return row.get(column, "")

    @staticmethod
    def _normalise_comment(value):
        """Ignore surrounding whitespace and platform-specific line endings only."""
        return (value or "").replace("\r\n", "\n").replace("\r", "\n").strip()

    @staticmethod
    def _contact_day(value):
        """Require an unambiguous ISO calendar date, without accepting timestamps."""
        day = date.fromisoformat(value)

        # fromisoformat also accepts compact and week dates; CSV dates must use
        # the documented calendar format so users can inspect them consistently.
        if day.isoformat() != value:
            raise ValueError("Use YYYY-MM-DD.")
        return day

    def _columns_matched(self, request):
        """Prepare a review page without persisting the proposed changes."""

        # Invalid proposals should return to the workflow without saving any data.
        try:
            context = self._prepare_changes(request)
        except ValueError as error:
            return HttpResponseBadRequest(str(error))
        return render(request, "upload/review.html", context)

    def _prepare_changes(self, request, lock=False) -> ImportReviewContext:
        """Build review data for contributor changes and separate history entries."""
        rows, mapping = self._read_import_data(request)
        name_column = next(column for column, field in mapping.items() if field == "contributor_name")
        names = [row.get(name_column, "") for row in rows]
        existing = self._find_contributors(names, lock=lock)
        changes = self._prepare_rows(request, rows, mapping, names, existing)
        return {
            "new_instances": changes["new_instances"],
            "modified_instances": changes["modified_instances"],
            "new_history_instances": changes["new_history_instances"],
            "duplicate_history_count": changes["duplicate_history_count"],
            "csv_path": request.POST.get("csv_path", ""),
            "csv_data_json": json.dumps(rows),
            "column_mapping_json": json.dumps(mapping),
            "contributor_type": self._contributor_type(request),
        }

    def _read_import_data(self, request) -> tuple[list[dict[str, str]], dict[str, str]]:
        """Decode and validate the CSV rows and mapping returned by the form."""

        # Review form values are untrusted JSON and may have been edited by the client.
        try:
            rows = json.loads(request.POST.get("csv_data", ""))
            mapping = json.loads(request.POST.get("column_mapping", ""))
        except (ValueError, TypeError):
            raise ValueError("Invalid CSV data or column mapping.")

        error = self._validate_csv_data(rows, mapping, self.CSV_FIELDS)

        # A malformed review payload must not reach model construction.
        if error is not None:
            raise ValueError(error)

        return rows, mapping

    @staticmethod
    def _find_contributors(names: list[str], lock=False) -> dict[str, Contributor]:
        """Find contributors by exact name, rejecting ambiguous matches."""
        existing: dict[str, Contributor] = {}
        contributors = Contributor.objects.filter(contributor_name__in=names).order_by("pk")

        # Review is read-only; confirmed imports need locks against competing updates.
        if lock:
            contributors = contributors.select_for_update()

        # Build exact-name identities before applying repeated CSV rows.
        for contributor in contributors:

            # An ambiguous name must never update an arbitrarily chosen contributor.
            if contributor.contributor_name in existing:
                raise ValueError("Multiple contributors share an uploaded name.")
            existing[contributor.contributor_name] = contributor
        return existing

    def _prepare_rows(self, request, rows, mapping, names, existing) -> ImportChanges:
        """Collect unsaved contributors and history, carrying changes across repeated names."""
        new_instances: list[Contributor] = []
        modified_instances: list[Contributor] = []
        new_history_instances: list[ContributorHistory] = []

        # Fetch existing contact comments once for all matched contributors.
        # Include contacts entered manually: their local calendar date, rather
        # than their time of day, identifies a date-only CSV contact.
        seen_contacts = {
            (name, timezone.localdate(timestamp), self._normalise_comment(details))
            for name, timestamp, details in ContributorHistory.objects.filter(
                contributor_id__in=[contributor.pk for contributor in existing.values()],
                event_category="Contact", event_type="Comment",
            ).values_list("contributor__contributor_name", "timestamp", "details")
        }
        duplicate_history_count = 0

        # Repeated names intentionally build on values proposed by earlier rows.
        for row, name in zip(rows, names):
            current = existing.get(name)
            selected_type = self._contributor_type(request)
            proposed = self._propose_contributor(current, selected_type or "")
            original_type = proposed.contributor_type
            changed = self._apply_mapped_values(proposed, row, mapping)
            if request.GET.get("contributor_type") and proposed.contributor_type != selected_type:
                raise PermissionDenied("The import must use the originating spreadsheet's contributor type.")
            if current is not None and proposed.contributor_type != original_type:
                raise PermissionDenied("Imports cannot change contributor type.")
            require_contributor(request.user, proposed, "import")
            if current is None or changed:
                require_contributor(request.user, proposed, "add" if current is None else "change")
            if self._mapped_value(row, mapping, "contact_history").strip():
                require_contributor(request.user, proposed, "contact")

            # The same set includes accepted rows from this file, so duplicates
            # are skipped both within an upload and on subsequent reuploads.
            history, duplicate = self._prepare_history(proposed, row, mapping, request.user, seen_contacts)
            if history is not None:
                new_history_instances.append(history)
            duplicate_history_count += duplicate

            # New contributors need creation; existing records must retain their identity.
            if current is None:
                new_instances.append(proposed)

            # History-only rows must not trigger unnecessary contributor writes.
            elif changed:
                modified_instances.append(proposed)

            # Later rows with the same name build on earlier proposed values.
            existing[name] = proposed

        return {
            "new_instances": new_instances,
            "modified_instances": modified_instances,
            "new_history_instances": new_history_instances,
            "duplicate_history_count": duplicate_history_count,
        }

    @staticmethod
    def _propose_contributor(current: Contributor | None, contributor_type: str) -> Contributor:
        """Create an unsaved contributor or copy existing values for review."""

        # New contributors need creation; existing records must retain their identity.
        if current is None:
            return Contributor(contributor_type=contributor_type)
        return Contributor(**{
            field.attname: getattr(current, field.attname)
            for field in Contributor._meta.concrete_fields
        })

    def _apply_mapped_values(self, proposed: Contributor, row: dict[str, str], mapping: dict[str, str]) -> bool:
        """Apply non-blank fields and merge socials, reporting whether values changed."""
        changed = False
        original_socials = self._read_socials(proposed.socials)
        socials = original_socials.copy()

        # Apply only the destinations explicitly chosen on the matching page.
        for column, field in mapping.items():
            value = row.get(column, "")

            # Blank CSV cells must not erase existing contributor details.
            if not value.strip():
                continue

            # Only the supported import fields may be assigned as model attributes.
            if field in self.CSV_FIELDS:

                # Unchanged values should not make a contributor appear modified in review.
                if getattr(proposed, field) != value:
                    setattr(proposed, field, value)
                    changed = True

            # Additional details merge by column name without replacing unrelated social entries.
            elif field == "__socials__" and socials.get(column) != value:
                socials[column] = value
                changed = True

        # Avoid replacing an unchanged JSON value or manufacturing an empty dictionary.
        if socials != original_socials:

            # JSONField accepts dictionaries despite the model's str annotation.
            setattr(proposed, "socials", socials)
        return changed

    @staticmethod
    def _read_socials(value: object) -> dict[str, object]:
        """Check the Python value already decoded by Django's JSONField."""

        # Records without social data start with an empty merge target.
        if value is None:
            return {}

        # Import cannot safely merge named entries into a legacy scalar JSON value.
        if not isinstance(value, dict):
            raise ValueError("Existing contributor socials must be a JSON object.")
        return value

    @staticmethod
    def _prepare_history(contributor, row, mapping, user, seen_contacts):
        """Append one dated contact per row; never edit an existing history entry."""
        comment = UploadCSV._normalise_comment(UploadCSV._mapped_value(row, mapping, "contact_history"))

        # Validation has already rejected incomplete contacts. Empty cells mean
        # no contact occurred and must not manufacture a new history entry.
        if not comment:
            return None, 0
        day = UploadCSV._contact_day(UploadCSV._mapped_value(row, mapping, "contact_date").strip())
        key = (contributor.contributor_name, day, comment)

        # Different notes on the same day remain distinct contacts. Text matching
        # preserves case and punctuation; changed prose is a new append-only note.
        if key in seen_contacts:
            return None, 1
        seen_contacts.add(key)

        # Existing history readers use timestamp as the contact occurrence time.
        # Store the supplied date at local midnight so last-contact dates and
        # contacted filters reflect the contact day, never the upload day.
        timestamp = timezone.make_aware(datetime.combine(day, time.min))
        return ContributorHistory(
            contributor=contributor, event_category="Contact", event_type="Comment",
            details=comment, timestamp=timestamp, user=user if user.is_authenticated else None,
        ), 0

    def _actions_reviewed(self, request):
        """Rebuild and save a confirmed import under locks in one transaction."""

        # Recompute proposals instead of trusting IDs or model changes from the review form.
        with transaction.atomic():

            # Revalidation under locks detects changes since the review was displayed.
            try:
                context = self._prepare_changes(request, lock=True)
            except ValueError as error:
                return HttpResponseBadRequest(str(error))
            self._save_import(context)
        destination = {"Sponsor": "TeamPages:SponsorEntryPoint", "Marketer": "CraftMarket:EntryPoint"}
        return redirect(destination.get(self._contributor_type(request), "contributors:spreadsheet"))

    @staticmethod
    def _save_import(context):
        """Resolve repeated contributors before attaching their imported notes."""
        saved: dict[str, Contributor] = {}

        # Repeated names represent successive updates to one contributor, not duplicates.
        for proposed in context["new_instances"] + context["modified_instances"]:
            previous = saved.get(proposed.contributor_name)

            # Repeated names must reuse the saved identity rather than create duplicate records.
            if previous is not None:
                proposed.pk = previous.pk
            proposed.save()
            saved[proposed.contributor_name] = proposed

        # New notes must reference saved instances, including repeated-name replacements.
        for history in context["new_history_instances"]:
            history.contributor = saved.get(history.contributor.contributor_name, history.contributor)
            history.save()
