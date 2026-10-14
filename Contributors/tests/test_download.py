import csv
import io

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from Contributors.models import Contributor
from Contributors.views.upload import UploadCSV


class DownloadCSVTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="download@example.com", password="test-password", phone="01234567890"
        )
        self.client.force_login(self.user)
        self.url = reverse("contributors:download")

    def test_exports_upload_fields_with_csv_escaping_and_blank_nulls(self):
        Contributor.objects.create(
            contributor_name='Élan, "Crafts"', contact_name="Alex", phone="07700900123",
            email=None, description="First line\nSecond line", contributor_type="Sponsor",
            socials={"Website": "https://example.com"},
        )
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertEqual(response["Content-Disposition"], 'attachment; filename="contributors.csv"')
        reader = csv.DictReader(io.StringIO(response.content.decode("utf-8")))
        self.assertEqual(reader.fieldnames, list(UploadCSV.CSV_FIELD_NAMES))
        self.assertEqual(list(reader), [{
            "contributor_name": 'Élan, "Crafts"', "contact_name": "Alex",
            "phone": "07700900123", "email": "", "description": "First line\nSecond line",
            "contributor_type": "Sponsor",
        }])

    def test_empty_export_has_headers(self):
        response = self.client.get(self.url)
        self.assertEqual(list(csv.reader(io.StringIO(response.content.decode()))),
                         [list(UploadCSV.CSV_FIELD_NAMES)])

    def test_download_requires_login(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_upload_and_spreadsheet_link_to_download(self):
        for name in ("upload", "spreadsheet"):
            with self.subTest(page=name):
                self.assertContains(self.client.get(reverse(f"contributors:{name}")),
                                    f'href="{self.url}"')
