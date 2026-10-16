from GarageSale.tests.access_helpers import grant_workflow_permissions
"""Acceptance tests for the three-stage CSV import and append-only contact history."""

import csv
import io
import json
from datetime import date, datetime
from html.parser import HTMLParser
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.html import escape
from django.utils import timezone

from Contributors.models import Contributor, ContributorHistory


class HiddenInputs(HTMLParser):
    """Read the browser's native POST values, including HTML-unescaped JSON."""

    def __init__(self, html):
        super().__init__()
        self.values = {}
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "input" and attrs.get("type") == "hidden" and "name" in attrs:
            self.values[attrs["name"]] = attrs.get("value", "")


class UploadCSVTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            email="upload@example.com", password="test-password", phone="01234567890"
        )
        grant_workflow_permissions(cls.user)
        cls.original = Contributor.objects.create(
            contributor_type="Sponsor", contributor_name="Oak & Co.",
            contact_name="Sam Taylor", phone="07700900123",
            email="sam@example.com", description="Existing description",
            socials={"Website": "https://old.example.com", "Legacy": "Keep me"},
        )
        cls.second = Contributor.objects.create(
            contributor_type="Sponsor", contributor_name="River Studio",
            contact_name="Alex Green", phone="07700900124",
            email="alex@example.com", description="River description", socials=None,
        )
        cls.unrelated = Contributor.objects.create(
            contributor_type="Sponsor", contributor_name="Untouched contributor",
            contact_name="Una", phone="07700900125", email="una@example.com",
            description="Must survive", socials={"Keep": "This too"},
        )

    def setUp(self):
        self.url = reverse("contributors:upload")
        self.client.force_login(self.user)

    def snapshot(self):
        return list(Contributor.objects.order_by("pk").values())

    def upload(self, content, filename="contributors.csv"):
        return self.client.post(self.url, {
            "stage": "select_file", "contributor_type": "Sponsor",
            "csv_file": SimpleUploadedFile(filename, content.encode("utf-8"), "text/csv"),
        })

    def review(self, rows, mapping, new_count, modified_count):
        """Exercise upload and matching; both must leave the database intact."""
        before = self.snapshot()
        headers = list(dict.fromkeys(key for row in rows for key in row))
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)
        filename = 'contributors & "partners".csv'
        uploaded = self.upload(stream.getvalue(), filename)
        self.assertEqual(uploaded.status_code, 200)
        self.assertTemplateUsed(uploaded, "upload/column_matching.html")
        self.assertEqual(uploaded.context["csv_path"], filename)
        parsed = uploaded.context["csv_data"]
        self.assertEqual(parsed, [{key: row.get(key, "") for key in headers} for row in rows])
        self.assertEqual(self.snapshot(), before)
        upload_inputs = HiddenInputs(uploaded.content.decode()).values
        self.assertEqual(upload_inputs["stage"], "match_columns")
        self.assertEqual(upload_inputs["csv_path"], filename)

        response = self.client.post(self.url, {
            "stage": "match_columns", "csv_path": upload_inputs["csv_path"],
            "csv_data": json.dumps(parsed), "column_mapping": json.dumps(mapping),
            "contributor_type": "Sponsor",
        })
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "upload/review.html")
        self.assertEqual(len(response.context["new_instances"]), new_count)
        self.assertEqual(len(response.context["modified_instances"]), modified_count)
        self.assertEqual(self.snapshot(), before, "Review must not save any changes")
        self.assertContains(response, "No contributors will be deleted")
        self.assertEqual(response.context["csv_path"], filename)
        payload = HiddenInputs(response.content.decode()).values
        self.assertEqual(payload["stage"], "review_changes")
        self.assertEqual(payload["csv_path"], filename)
        self.assertEqual(json.loads(payload["csv_data"]), parsed)
        self.assertEqual(json.loads(payload["column_mapping"]), mapping)
        return response, payload

    def confirm(self, payload):
        unrelated_before = Contributor.objects.filter(pk=self.unrelated.pk).values().get()
        existing_ids = set(Contributor.objects.values_list("pk", flat=True))
        response = self.client.post(self.url, {**payload, "contributor_type": "Sponsor"})
        self.assertIn(response.status_code, (200, 302, 303))
        self.assertTrue(existing_ids <= set(Contributor.objects.values_list("pk", flat=True)))
        self.assertEqual(Contributor.objects.filter(pk=self.unrelated.pk).values().get(), unrelated_before)
        return response

    def test_get_starts_at_file_selection(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "upload/upload.html")
        self.assertContains(response, 'enctype="multipart/form-data"')
        self.assertEqual(HiddenInputs(response.content.decode()).values["stage"], "select_file")

    def test_csv_upload_reads_headers_and_passes_data_to_column_matching(self):
        content = '"Contributor, name",Email\nOak & Co.,oak@example.com\n'
        mapping = {"Contributor, name": "contributor_name", "Email": "email"}
        csv_path = "/uploads/Sponsors & Partners/contributors.csv"
        payloads = (
            {"csv_path": csv_path, "csv_data": content},
            {"csv_file": SimpleUploadedFile("contributors.csv", content.encode(), "text/csv")},
        )
        for payload in payloads:
            with self.subTest(source="POST" if "csv_data" in payload else "FILES"):
                before = self.snapshot()
                with patch("Contributors.views.upload.UploadCSV._match_names", return_value=mapping) as match_names:
                    response = self.client.post(self.url, {"stage": "select_file", **payload})
                match_names.assert_called_once_with(["Contributor, name", "Email"])
                self.assertEqual(response.status_code, 200)
                self.assertTemplateUsed(response, "upload/column_matching.html")
                self.assertEqual(response.context["csv_path"], payload.get("csv_path", "contributors.csv"))
                self.assertEqual(response.context["csv_data"], [
                    {"Contributor, name": "Oak & Co.", "Email": "oak@example.com"},
                ])
                self.assertEqual(response.context["possible_matches"], mapping)
                self.assertEqual(self.snapshot(), before)

    def test_column_matching_has_native_abort_link(self):
        request = RequestFactory().get(self.url)
        request.user = self.user
        html = render_to_string("upload/column_matching.html", {
            "csv_path": "wrong-file.csv", "csv_data": [{"Unrelated": "Data"}],
            "possible_matches": {}, "csrf_token": "test-token",
        }, request=request)
        self.assertInHTML(f'<a href="{self.url}">Abort upload</a>', html)

    def test_column_matching_displays_file_path(self):
        request = RequestFactory().get(self.url)
        request.user = self.user
        csv_path = '/uploads/Sponsors & Partners/"contributors".csv'
        html = render_to_string("upload/column_matching.html", {
            "csv_path": csv_path, "csv_filename": "contributors.csv",
            "csv_data": [{"contributor_name": "Oak & Co."}],
            "possible_matches": {}, "csrf_token": "test-token",
        }, request=request)

        self.assertInHTML(
            '<span class="file-path"><span class="muted">File path:</span> '
            f'<strong>{escape(csv_path)}</strong></span>',
            html,
        )
        self.assertEqual(HiddenInputs(html).values["csv_path"], csv_path)

    def test_abort_returns_to_file_selection_without_saving(self):
        before = self.snapshot()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "upload/upload.html")
        self.assertEqual(self.snapshot(), before)

    def test_empty_csv_files_are_rejected(self):
        for content in ("", "\n\n", "contributor_name,email\n"):
            with self.subTest(content=content):
                before = self.snapshot()
                response = self.upload(content)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(self.snapshot(), before)

    def test_unknown_headers_allow_manual_mapping(self):
        uploaded = self.upload("Mystery A,Mystery B\nMeadow Crafts,meadow@example.com\n")
        self.assertEqual(uploaded.status_code, 200)
        self.assertFalse(any(uploaded.context["possible_matches"].values()))
        _, payload = self.review(
            [{"Mystery A": "Meadow Crafts", "Mystery B": "meadow@example.com"}],
            {"Mystery A": "contributor_name", "Mystery B": "email"}, 1, 0,
        )
        self.confirm(payload)
        self.assertEqual(Contributor.objects.get(contributor_name="Meadow Crafts").email, "meadow@example.com")

    def test_all_unmatched_names_create_new_contributors(self):
        _, payload = self.review(
            [{"contributor_name": "Meadow Crafts"}, {"contributor_name": "Hill Gifts"}],
            {"contributor_name": "contributor_name"}, 2, 0,
        )
        before = self.snapshot()
        self.confirm(payload)
        self.assertEqual(Contributor.objects.count(), 5)
        self.assertEqual(list(Contributor.objects.filter(pk__in=[row["id"] for row in before]).order_by("pk").values()), before)

    def test_valid_csv_creates_new_contributor(self):
        _, payload = self.review(
            [{"contributor_name": "Meadow Crafts", "contact_name": "Jo", "phone": "07700900126", "email": "jo@example.com"}],
            {key: key for key in ("contributor_name", "contact_name", "phone", "email")}, 1, 0,
        )
        self.confirm(payload)
        created = Contributor.objects.get(contributor_name="Meadow Crafts")
        self.assertEqual((created.contact_name, created.phone, created.email), ("Jo", "07700900126", "jo@example.com"))
        self.assertEqual(Contributor.objects.count(), 4)

    def test_contact_history_comments_are_reviewed_then_appended(self):
        old = ContributorHistory.objects.create(
            contributor=self.original, event_category="Contact", event_type="Comment",
            details="Existing comment", user=self.user,
        )
        before = list(ContributorHistory.objects.values())
        response, payload = self.review([
            {"Name": "Oak & Co.", "Notes": " First comment\r\n\n Second comment \n", "Date": "2026-10-12", "Email": ""},
            {"Name": "Meadow Crafts", "Notes": "New contributor comment", "Date": "2026-10-13", "Email": "jo@example.com"},
        ], {"Name": "contributor_name", "Notes": "contact_history", "Date": "contact_date", "Email": "email"}, 1, 0)
        self.assertEqual(list(ContributorHistory.objects.values()), before)
        self.assertContains(response, "First comment")
        self.assertContains(response, "Second comment")
        histories = response.context["new_history_instances"]
        self.assertEqual([history.details for history in histories],
                         ["First comment\n\n Second comment", "New contributor comment"])
        self.assertEqual([timezone.localdate(history.timestamp) for history in histories],
                         [date(2026, 10, 12), date(2026, 10, 13)])
        for history in histories:
            self.assertIsInstance(history, ContributorHistory)
            self.assertIsNone(history.pk)
            self.assertFalse(hasattr(history.contributor, "contact_history"))
        self.assertNotIn('value="Confirm import" disabled', response.content.decode())
        self.confirm(payload)
        self.original.refresh_from_db()
        self.assertEqual(self.original.email, "sam@example.com")
        self.assertEqual(list(ContributorHistory.objects.filter(contributor=self.original)
                              .order_by("pk").values_list("details", flat=True)),
                         ["Existing comment", "First comment\n\n Second comment"])
        new = Contributor.objects.get(contributor_name="Meadow Crafts")
        comment = ContributorHistory.objects.get(contributor=new)
        self.assertEqual((comment.details, comment.event_category, comment.event_type, comment.user),
                         ("New contributor comment", "Contact", "Comment", self.user))
        old.refresh_from_db()
        self.assertEqual(old.details, "Existing comment")

    def test_blank_ignored_and_unmapped_contact_history_add_no_entries(self):
        for destination, notes in (("contact_history", " \r\n\n "), ("", "Ignore me"), ("__ignore__", "Ignore me")):
            with self.subTest(destination=destination):
                response, payload = self.review([
                    {"Name": "Oak & Co.", "Notes": notes},
                ], {"Name": "contributor_name", "Notes": destination}, 0, 0)
                self.confirm(payload)
                self.assertFalse(ContributorHistory.objects.exists())

    def test_history_only_import_does_not_save_contributor(self):
        response, payload = self.review([
            {"Name": "Oak & Co.", "Notes": "Called today", "Date": "2026-10-16"},
        ], {"Name": "contributor_name", "Notes": "contact_history", "Date": "contact_date"}, 0, 0)
        self.assertNotIn('value="Confirm import" disabled', response.content.decode())
        with patch.object(Contributor, "save", side_effect=AssertionError("Contributor must remain unchanged")):
            self.confirm(payload)
        history = ContributorHistory.objects.get(contributor=self.original)
        self.assertEqual(history.details, "Called today")
        self.assertEqual(timezone.localdate(history.timestamp), date(2026, 10, 16))

    def test_overlong_contact_history_is_rejected_before_saving(self):
        before = self.snapshot()
        for stage in ("match_columns", "review_changes"):
            with self.subTest(stage=stage):
                response = self.client.post(self.url, {
                    "stage": stage,
                    "csv_data": json.dumps([{"Name": "Oak & Co.", "Notes": "x" * 1001}]),
                    "column_mapping": json.dumps({"Name": "contributor_name", "Notes": "contact_history"}),
                })
                self.assertEqual(response.status_code, 400)
                self.assertEqual(self.snapshot(), before)
                self.assertFalse(ContributorHistory.objects.exists())

    def test_same_day_contacts_are_distinct_but_exact_duplicates_are_skipped(self):
        rows = [
            {"Name": "Oak & Co.", "Date": "2026-10-16", "Notes": "Called; no answer."},
            {"Name": "Oak & Co.", "Date": "2026-10-16", "Notes": "Jane called back."},
            {"Name": "Oak & Co.", "Date": "2026-10-16", "Notes": " Called; no answer. \r\n"},
            {"Name": "Oak & Co.", "Date": "2026-10-17", "Notes": "Called; no answer."},
        ]
        mapping = {"Name": "contributor_name", "Date": "contact_date", "Notes": "contact_history"}
        response, payload = self.review(rows, mapping, 0, 0)
        self.assertEqual(len(response.context["new_history_instances"]), 3)
        self.assertEqual(response.context["duplicate_history_count"], 1)
        self.assertContains(response, "1 duplicate contact skipped")
        self.assertContains(response, "2026-10-16")
        self.confirm(payload)
        before = list(ContributorHistory.objects.order_by("pk").values())
        response, payload = self.review(rows, mapping, 0, 0)
        self.assertEqual(response.context["new_history_instances"], [])
        self.assertEqual(response.context["duplicate_history_count"], 4)
        self.confirm(payload)
        self.assertEqual(list(ContributorHistory.objects.order_by("pk").values()), before)

    def test_existing_manual_contact_uses_local_date_and_normalised_multiline_note(self):
        timestamp = timezone.make_aware(datetime(2026, 7, 16, 0, 30))
        old = ContributorHistory.objects.create(
            contributor=self.original, event_category="Contact", event_type="Comment",
            details=" Called Jane\r\nSent details. ", timestamp=timestamp, user=self.user,
        )
        response, payload = self.review([
            {"Name": "Oak & Co.", "Date": "2026-07-16", "Notes": "Called Jane\nSent details."},
        ], {"Name": "contributor_name", "Date": "contact_date", "Notes": "contact_history"}, 0, 0)
        self.assertEqual(response.context["duplicate_history_count"], 1)
        self.assertEqual(response.context["new_history_instances"], [])
        self.confirm(payload)
        old.refresh_from_db()
        self.assertEqual(old.timestamp, timestamp)
        self.assertEqual(old.details, " Called Jane\r\nSent details. ")

    def test_duplicate_check_preserves_case_punctuation_and_contributor_identity(self):
        rows = [
            {"Name": name, "Date": "2026-10-16", "Notes": note}
            for name, note in [
                ("Oak & Co.", "Called"), ("Oak & Co.", "called"),
                ("Oak & Co.", "Called."), ("River Studio", "Called"),
            ]
        ]
        response, payload = self.review(rows, {
            "Name": "contributor_name", "Date": "contact_date", "Notes": "contact_history",
        }, 0, 0)
        self.assertEqual(len(response.context["new_history_instances"]), 4)
        self.assertEqual(response.context["duplicate_history_count"], 0)
        self.confirm(payload)
        self.assertEqual(ContributorHistory.objects.count(), 4)

    def test_confirmation_rechecks_contacts_added_since_review(self):
        response, payload = self.review([
            {"Name": "Oak & Co.", "Date": "2026-10-16", "Notes": "Called Jane"},
        ], {"Name": "contributor_name", "Date": "contact_date", "Notes": "contact_history"}, 0, 0)
        proposed = response.context["new_history_instances"][0]
        ContributorHistory.objects.create(
            contributor=self.original, event_category="Contact", event_type="Comment",
            details=proposed.details, timestamp=proposed.timestamp,
        )
        self.confirm(payload)
        self.assertEqual(ContributorHistory.objects.count(), 1)

    def test_repeated_new_contributor_contacts_share_identity_and_skip_duplicates(self):
        rows = [
            {"Name": "New sponsor", "Date": "2026-10-16", "Notes": note}
            for note in ["Called", "Emailed", "Called"]
        ]
        response, payload = self.review(rows, {
            "Name": "contributor_name", "Date": "contact_date", "Notes": "contact_history",
        }, 1, 0)
        self.assertEqual(response.context["duplicate_history_count"], 1)
        self.confirm(payload)
        new = Contributor.objects.get(contributor_name="New sponsor")
        self.assertEqual(ContributorHistory.objects.filter(contributor=new).count(), 2)

    def test_invalid_or_incomplete_contact_dates_reject_both_stages_without_writes(self):
        mapping = {"Name": "contributor_name", "Date": "contact_date", "Notes": "contact_history"}
        for stage in ("match_columns", "review_changes"):
            for day, note in [
                ("", "Called"), ("2026-10-16", ""), ("16/10/2026", "Called"),
                ("2026-02-30", "Called"), ("20261016", "Called"),
                ("2026-10-16T12:00:00", "Called"),
            ]:
                with self.subTest(stage=stage, day=day, note=note):
                    before = self.snapshot()
                    response = self.client.post(self.url, {
                        "stage": stage,
                        "csv_data": json.dumps([{"Name": "Oak & Co.", "Date": day, "Notes": note}]),
                        "column_mapping": json.dumps(mapping),
                    })
                    self.assertEqual(response.status_code, 400)
                    self.assertEqual(self.snapshot(), before)
                    self.assertFalse(ContributorHistory.objects.exists())

    def test_whole_multiline_note_must_fit_history_field(self):
        response = self.client.post(self.url, {
            "stage": "match_columns",
            "csv_data": json.dumps([{"Name": "Oak & Co.", "Date": "2026-10-16",
                                     "Notes": "a" * 600 + "\n" + "b" * 600}]),
            "column_mapping": json.dumps({"Name": "contributor_name", "Date": "contact_date",
                                          "Notes": "contact_history"}),
        })
        self.assertEqual(response.status_code, 400)
        self.assertFalse(ContributorHistory.objects.exists())

    def test_column_matching_reviews_new_modified_and_unchanged_rows_without_saving(self):
        response, _ = self.review([
            {"Name": "Meadow Crafts", "Email": "jo@example.com", "Website": "https://meadow.example.com"},
            {"Name": "Oak & Co.", "Email": "new@example.com", "Website": "https://new.example.com", "Instagram": "@oak", "Phone": "", "Ignored": "Discard", "Unmapped": "Discard"},
            {"Name": "River Studio", "Email": "alex@example.com", "Website": ""},
        ], {
            "Name": "contributor_name", "Email": "email", "Phone": "phone",
            "Website": "__socials__", "Instagram": "__socials__",
            "Ignored": "__ignore__", "Unmapped": "",
        }, 1, 1)
        new = response.context["new_instances"][0]
        self.assertIsNone(new.pk)
        self.assertEqual((new.contributor_name, new.email, new.contributor_type),
                         ("Meadow Crafts", "jo@example.com", "Sponsor"))
        self.assertEqual(new.socials, {"Website": "https://meadow.example.com"})
        modified = response.context["modified_instances"][0]
        self.assertEqual(modified.pk, self.original.pk)
        self.assertEqual(modified.email, "new@example.com")
        self.assertEqual(modified.phone, self.original.phone)
        self.assertEqual(modified.contact_name, self.original.contact_name)
        self.assertEqual(modified.socials, {
            "Legacy": "Keep me", "Website": "https://new.example.com", "Instagram": "@oak",
        })

    def test_valid_csv_modifies_existing_contributor(self):
        _, payload = self.review(
            [{"contributor_name": "Oak & Co.", "email": "new@example.com"}],
            {"contributor_name": "contributor_name", "email": "email"}, 0, 1,
        )
        before = Contributor.objects.filter(pk=self.original.pk).values().get()
        self.confirm(payload)
        self.assertEqual(Contributor.objects.filter(pk=self.original.pk).values().get(), {**before, "email": "new@example.com"})
        self.assertEqual(Contributor.objects.count(), 3)

    def test_valid_csv_modifies_multiple_columns(self):
        values = {"contributor_name": "Oak & Co.", "contact_name": "Robin", "phone": "07700900129", "email": "robin@example.com"}
        _, payload = self.review([values], {key: key for key in values}, 0, 1)
        before = Contributor.objects.filter(pk=self.original.pk).values().get()
        self.confirm(payload)
        self.assertEqual(Contributor.objects.filter(pk=self.original.pk).values().get(), {**before, **values})

    def test_one_csv_creates_and_updates_single_and_multiple_columns(self):
        rows = [
            {"contributor_name": "Meadow Crafts", "contact_name": "Jo", "phone": "07700900126", "email": "jo@example.com"},
            {"contributor_name": "Oak & Co.", "email": "new@example.com"},
            {"contributor_name": "River Studio", "contact_name": "Robin", "phone": "07700900129", "email": "robin@example.com"},
        ]
        _, payload = self.review(rows, {key: key for key in rows[0]}, 1, 2)
        oak_before = Contributor.objects.filter(pk=self.original.pk).values().get()
        river_before = Contributor.objects.filter(pk=self.second.pk).values().get()
        self.confirm(payload)
        self.assertEqual(Contributor.objects.count(), 4)
        self.assertEqual(Contributor.objects.filter(pk=self.original.pk).values().get(), {**oak_before, **rows[1]})
        self.assertEqual(Contributor.objects.filter(pk=self.second.pk).values().get(), {**river_before, **rows[2]})
        created = Contributor.objects.get(contributor_name="Meadow Crafts")
        self.assertEqual((created.contact_name, created.phone, created.email), ("Jo", "07700900126", "jo@example.com"))

    def test_blank_values_preserve_existing_fields(self):
        values = {"contributor_name": "Oak & Co.", "contact_name": "", "phone": "", "email": "new@example.com"}
        _, payload = self.review([values], {key: key for key in values}, 0, 1)
        before = Contributor.objects.filter(pk=self.original.pk).values().get()
        self.confirm(payload)
        self.assertEqual(Contributor.objects.filter(pk=self.original.pk).values().get(), {**before, "email": "new@example.com"})

    def test_socials_merge_preserves_unrelated_keys_and_updates_matching_keys(self):
        response, payload = self.review(
            [{"contributor_name": "Oak & Co.", "Instagram": "@oak", "Website": "https://new.example.com"}],
            {"contributor_name": "contributor_name", "Instagram": "__socials__", "Website": "__socials__"}, 0, 1,
        )
        proposed = response.context["modified_instances"][0]
        proposed_socials = proposed["socials"] if isinstance(proposed, dict) else proposed.socials
        self.assertEqual(proposed_socials, {"Legacy": "Keep me", "Instagram": "@oak", "Website": "https://new.example.com"})
        self.confirm(payload)
        self.original.refresh_from_db()
        self.assertEqual(self.original.socials, {"Legacy": "Keep me", "Instagram": "@oak", "Website": "https://new.example.com"})

    def test_blank_socials_values_preserve_existing_keys(self):
        _, payload = self.review(
            [{"contributor_name": "Oak & Co.", "Website": "", "Instagram": "@oak"}],
            {"contributor_name": "contributor_name", "Website": "__socials__", "Instagram": "__socials__"}, 0, 1,
        )
        self.confirm(payload)
        self.original.refresh_from_db()
        self.assertEqual(self.original.socials, {"Website": "https://old.example.com", "Legacy": "Keep me", "Instagram": "@oak"})

    def test_socials_merge_handles_null_existing_data(self):
        _, payload = self.review(
            [{"contributor_name": "River Studio", "Instagram": "@river"}],
            {"contributor_name": "contributor_name", "Instagram": "__socials__"}, 0, 1,
        )
        self.confirm(payload)
        self.second.refresh_from_db()
        self.assertEqual(self.second.socials, {"Instagram": "@river"})

    def test_socials_merge_rejects_non_object_json_without_saving(self):
        for socials in ([], "", '{"Website": "https://old.example.com"}'):
            with self.subTest(socials=socials):
                Contributor.objects.filter(pk=self.original.pk).update(socials=socials)
                before = self.snapshot()
                for stage in ("match_columns", "review_changes"):
                    response = self.client.post(self.url, {
                        "stage": stage,
                        "csv_data": json.dumps([{"Name": "Oak & Co.", "Website": "https://new.example.com"}]),
                        "column_mapping": json.dumps({"Name": "contributor_name", "Website": "__socials__"}),
                    })
                    self.assertEqual(response.status_code, 400)
                    self.assertEqual(self.snapshot(), before)

    def test_new_contributor_receives_socials_keys(self):
        _, payload = self.review(
            [{"contributor_name": "Meadow Crafts", "Instagram": "@meadow", "Website": ""}],
            {"contributor_name": "contributor_name", "Instagram": "__socials__", "Website": "__socials__"}, 1, 0,
        )
        self.confirm(payload)
        self.assertEqual(Contributor.objects.get(contributor_name="Meadow Crafts").socials, {"Instagram": "@meadow"})

    def test_ignored_and_unmapped_columns_are_carried_but_not_saved(self):
        _, payload = self.review(
            [{"contributor_name": "Oak & Co.", "email": "new@example.com", "phone": "DO NOT SAVE", "Legacy": "DO NOT SAVE"}],
            {"contributor_name": "contributor_name", "email": "email", "phone": "__ignore__", "Legacy": ""}, 0, 1,
        )
        before = Contributor.objects.filter(pk=self.original.pk).values().get()
        self.confirm(payload)
        self.assertEqual(Contributor.objects.filter(pk=self.original.pk).values().get(), {**before, "email": "new@example.com"})

    def test_unchanged_rows_are_not_listed_as_modified(self):
        response, _ = self.review(
            [{"contributor_name": "Oak & Co.", "email": "sam@example.com"}],
            {"contributor_name": "contributor_name", "email": "email"}, 0, 0,
        )
        self.assertContains(response, "No contributors will be modified.")

    def test_missing_or_unknown_stage_is_rejected(self):
        for stage in (None, "", "unexpected", "2"):
            with self.subTest(stage=stage):
                before = self.snapshot()
                response = self.client.post(self.url, {} if stage is None else {"stage": stage})
                self.assertEqual(response.status_code, 400)
                self.assertEqual(self.snapshot(), before)

    def test_missing_name_mapping_is_rejected(self):
        before = self.snapshot()
        response = self.client.post(self.url, {
            "stage": "match_columns", "csv_path": "contributors.csv",
            "csv_data": json.dumps([{"email": "new@example.com"}]),
            "column_mapping": json.dumps({"email": "email"}),
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.snapshot(), before)

    def test_missing_uploaded_file_is_rejected(self):
        before = self.snapshot()
        response = self.client.post(self.url, {"stage": "select_file"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.snapshot(), before)

    def test_confirmation_revalidates_invalid_payload(self):
        for csv_data in ("not JSON", "[]", '[{"contributor_name": ""}]'):
            with self.subTest(csv_data=csv_data):
                before = self.snapshot()
                response = self.client.post(self.url, {
                    "stage": "review_changes", "csv_path": "contributors.csv",
                    "csv_data": csv_data,
                    "column_mapping": json.dumps({"contributor_name": "contributor_name"}),
                })
                self.assertEqual(response.status_code, 400)
                self.assertEqual(self.snapshot(), before)
