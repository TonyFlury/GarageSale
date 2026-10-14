import csv
import io
import json
from typing import TypedDict

from django.http import HttpResponseBadRequest
from django.db import transaction
from django.shortcuts import redirect, render
from django.views import View

from Contributors.models import Contributor, ContributorHistory


class ImportChanges(TypedDict):
    """Model instances prepared for saving after confirmation."""

    new_instances: list[Contributor]
    modified_instances: list[Contributor]
    new_history_instances: list[ContributorHistory]


class ImportReviewContext(ImportChanges):
    """Prepared instances and serialized form values used by the review page."""

    csv_path: str
    csv_data_json: str
    column_mapping_json: str
    contributor_type: str | None


class UploadCSV(View):
    """Handle file selection, column matching, and action review at one URL."""

    CSV_FIELD_NAMES = ("contributor_name", "contact_name", "phone", "email", "description", "contributor_type")
    CSV_FIELDS = set(CSV_FIELD_NAMES)

    def get(self, request, *args, **kwargs):
        return render(request, "upload/upload.html")

    def post(self, request, *args, **kwargs):
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
        csv_path = request.POST.get("csv_path")
        csv_data = request.POST.get("csv_data")
        uploaded_file = request.FILES.get("csv_file")
        if uploaded_file is not None:
            csv_path = csv_path or uploaded_file.name
            try:
                csv_data = uploaded_file.read().decode("utf-8-sig")
            except UnicodeDecodeError:
                return HttpResponseBadRequest("CSV file must use UTF-8 encoding.")
        if not csv_path or not csv_data:
            return HttpResponseBadRequest("Missing CSV file path or data.")

        try:
            reader = csv.DictReader(io.StringIO(csv_data.lstrip("\ufeff")), strict=True)
            columns = reader.fieldnames
            rows = list(reader)
        except csv.Error:
            return HttpResponseBadRequest("Invalid CSV data.")
        if not columns or not rows:
            return HttpResponseBadRequest("CSV must contain headers and at least one data row.")

        return render(request, "upload/column_matching.html", {
            "csv_path": csv_path,
            "csv_data": rows,
            "possible_matches": self._match_names(columns),
            "contributor_type": request.POST.get("contributor_type"),
        })

    @staticmethod
    def _match_names(columns):
        """Return a mapping from CSV column names to model field names."""
        # TODO: Match CSV column names to Contributor fields.
        return {}

    @staticmethod
    def _validate_csv_data(rows, mapping, fields):
        """Return a validation error message, or None for valid CSV data."""
        if not isinstance(rows, list):
            return "Invalid CSV data or column mapping."
        if not rows:
            return "Invalid CSV data or column mapping."
        for row in rows:
            if not isinstance(row, dict):
                return "Invalid CSV data or column mapping."
            for key, value in row.items():
                if not isinstance(key, str):
                    return "Invalid CSV data or column mapping."
                if not isinstance(value, str):
                    return "Invalid CSV data or column mapping."

        if not isinstance(mapping, dict):
            return "Invalid CSV data or column mapping."
        allowed_destinations = fields | {"", "__ignore__", "__socials__", "contact_history"}
        for column, field in mapping.items():
            if not isinstance(column, str):
                return "Invalid CSV data or column mapping."
            if not isinstance(field, str):
                return "Invalid CSV data or column mapping."
            if field not in allowed_destinations:
                return "Invalid CSV data or column mapping."

        mapped_fields = [field for field in mapping.values() if field in fields | {"contact_history"}]
        if "contributor_name" not in mapped_fields:
            return "Map contributor name and select each model field only once."
        if len(mapped_fields) != len(set(mapped_fields)):
            return "Map contributor name and select each model field only once."
        name_column = next(column for column, field in mapping.items() if field == "contributor_name")
        for row in rows:
            if not row.get(name_column, "").strip():
                return "Each CSV row must have a contributor name."
            for column, destination in mapping.items():
                if destination == "contact_history":
                    if any(len(line.strip()) > 1000 for line in row.get(column, "").splitlines()):
                        return "Contact History comments must be 1000 characters or fewer."
        return None

    def _columns_matched(self, request):
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
            "csv_path": request.POST.get("csv_path", ""),
            "csv_data_json": json.dumps(rows),
            "column_mapping_json": json.dumps(mapping),
            "contributor_type": request.POST.get("contributor_type"),
        }

    def _read_import_data(self, request) -> tuple[list[dict[str, str]], dict[str, str]]:
        """Decode and validate the CSV rows and mapping returned by the form."""
        try:
            rows = json.loads(request.POST.get("csv_data", ""))
            mapping = json.loads(request.POST.get("column_mapping", ""))
        except (ValueError, TypeError):
            raise ValueError("Invalid CSV data or column mapping.")

        error = self._validate_csv_data(rows, mapping, self.CSV_FIELDS)
        if error is not None:
            raise ValueError(error)

        return rows, mapping

    @staticmethod
    def _find_contributors(names: list[str], lock=False) -> dict[str, Contributor]:
        """Find contributors by exact name, rejecting ambiguous matches."""
        existing: dict[str, Contributor] = {}
        contributors = Contributor.objects.filter(contributor_name__in=names).order_by("pk")
        if lock:
            contributors = contributors.select_for_update()
        for contributor in contributors:
            if contributor.contributor_name in existing:
                raise ValueError("Multiple contributors share an uploaded name.")
            existing[contributor.contributor_name] = contributor
        return existing

    def _prepare_rows(self, request, rows, mapping, names, existing) -> ImportChanges:
        """Collect unsaved contributors and history, carrying changes across repeated names."""
        new_instances: list[Contributor] = []
        modified_instances: list[Contributor] = []
        new_history_instances: list[ContributorHistory] = []
        for row, name in zip(rows, names):
            current = existing.get(name)
            proposed = self._propose_contributor(current, request.POST.get("contributor_type", ""))
            changed = self._apply_mapped_values(proposed, row, mapping)
            new_history_instances.extend(self._prepare_history(proposed, row, mapping, request.user))
            if current is None:
                new_instances.append(proposed)
            elif changed:
                modified_instances.append(proposed)
            # Later rows with the same name build on earlier proposed values.
            existing[name] = proposed

        return {
            "new_instances": new_instances,
            "modified_instances": modified_instances,
            "new_history_instances": new_history_instances,
        }

    @staticmethod
    def _propose_contributor(current: Contributor | None, contributor_type: str) -> Contributor:
        """Create an unsaved contributor or copy existing values for review."""
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
        for column, field in mapping.items():
            value = row.get(column, "")
            if not value.strip():
                continue
            if field in self.CSV_FIELDS:
                if getattr(proposed, field) != value:
                    setattr(proposed, field, value)
                    changed = True
            elif field == "__socials__" and socials.get(column) != value:
                socials[column] = value
                changed = True
        if socials != original_socials:
            # JSONField accepts dictionaries despite the model's str annotation.
            setattr(proposed, "socials", socials)
        return changed

    @staticmethod
    def _read_socials(value: object) -> dict[str, object]:
        """Check the Python value already decoded by Django's JSONField."""
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ValueError("Existing contributor socials must be a JSON object.")
        return value

    @staticmethod
    def _prepare_history(contributor: Contributor, row: dict[str, str], mapping: dict[str, str], user) -> list[ContributorHistory]:
        """Create a separate unsaved history entry for each non-blank comment line."""
        histories: list[ContributorHistory] = []
        for column, destination in mapping.items():
            if destination != "contact_history":
                continue
            for line in row.get(column, "").splitlines():
                comment = line.strip()
                if comment:
                    histories.append(ContributorHistory(
                        contributor=contributor, event_category="Contact", event_type="Comment",
                        details=comment, user=user if user.is_authenticated else None,
                    ))
        return histories

    def _actions_reviewed(self, request):
        """Validate and save the confirmed import in a single transaction.

        Rebuild proposed changes from the submitted CSV data and mapping,
        locking existing contributors while applying updates. Save new and
        modified contributors, then add each contact comment as a separate
        ContributorHistory entry linked to its saved contributor. Preserve
        existing history and leave history-only contributors unchanged.

        Return HTTP 400 for invalid import data; redirect to the contributor
        spreadsheet after a successful import.
        """
        with transaction.atomic():
            try:
                context = self._prepare_changes(request, lock=True)
            except ValueError as error:
                return HttpResponseBadRequest(str(error))
            saved: dict[str, Contributor] = {}
            for proposed in context["new_instances"] + context["modified_instances"]:
                previous = saved.get(proposed.contributor_name)
                if previous is not None:
                    proposed.pk = previous.pk
                proposed.save()
                saved[proposed.contributor_name] = proposed
            for history in context["new_history_instances"]:
                history.contributor = saved.get(history.contributor.contributor_name, history.contributor)
                history.save()
        return redirect("contributors:spreadsheet")
