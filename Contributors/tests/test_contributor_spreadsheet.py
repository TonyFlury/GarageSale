from GarageSale.tests.access_helpers import grant_workflow_permissions
import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from Contributors.models import Contributor, ContributorHistory


class ContributorSpreadsheetViewTests(TestCase):
    """Test the various REST APIS used by the Contributor Spreadsheet"""
    def setUp(self):
        User = get_user_model()

        self.user = User.objects.create_user(
            email="admin@example.com",
            password="password123",
            phone="01234567890",
        )
        grant_workflow_permissions(self.user)

        self.contributor = Contributor.objects.create(
            contributor_type="Sponsor",
            contributor_name="Acme Ltd",
            contact_name="Alex Smith",
            phone="01234567890",
            email="alex@example.com",
            description="Original description",
        )

    def test_spreadsheet_requires_login(self):
        response = self.client.get(reverse("contributors:spreadsheet"))

        self.assertEqual(response.status_code, 302)

    def test_create_contributor(self):
        """Test that the create endpoint creates a new contributor"""
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("contributors:spreadsheet_create"),
            data=json.dumps(
                {
                    "contributor_type": "Sponsor",
                    "contributor_name": "New Company Ltd",
                    "contact_name": "New Contact",
                    "phone": "07111111111",
                    "email": "new@example.com",
                    "description": "A newly created contributor.",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)

        body = response.json()

        self.assertTrue(body["ok"])
        self.assertTrue(body["created"])
        self.assertEqual(body["contributor"]["contributor_name"], "New Company Ltd")
        self.assertIn("save_url", body["contributor"])

        self.assertTrue(
            Contributor.objects.filter(
                contributor_name="New Company Ltd",
                email="new@example.com",
            ).exists()
        )
        contributor = Contributor.objects.filter(contributor_name="New Company Ltd").first()

        # Need to show that the ContributorHistory is also created
        history = ContributorHistory.objects.filter(contributor=contributor)
        self.assertEqual(history.count(), 1)
        self.assertEqual(history[0].event_category, "Data")
        self.assertEqual(history[0].event_type, "New")


    def test_create_rejects_invalid_data(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("contributors:spreadsheet_create"),
            data=json.dumps(
                {
                    "contributor_type": "",
                    "contributor_name": "",
                    "contact_name": "",
                    "phone": "",
                    "email": "bad-email",
                    "description": "",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)

        body = response.json()

        self.assertFalse(body["ok"])
        self.assertIn("contributor_type", body["errors"])
        self.assertIn("contributor_name", body["errors"])
        self.assertIn("email", body["errors"])


    def test_spreadsheet_displays_contributors(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("contributors:spreadsheet"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Acme Ltd")
        self.assertContains(response, "Alex Smith")
        self.assertContains(response, "alex@example.com")

    def test_save_requires_login(self):
        response = self.client.post(
            reverse("contributors:spreadsheet_save", args=[self.contributor.pk]),
            data=json.dumps({}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 302)

    # This needs to ensure that a history is recorded.
    def test_save_updates_contributor(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("contributors:spreadsheet_save", args=[self.contributor.pk]),
            data=json.dumps(
                {
                    "contributor_type": "Sponsor",
                    "contributor_name": "Updated Company",
                    "contact_name": "Jordan Jones",
                    "phone": "07123456789",
                    "email": "jordan@example.com",
                    "description": "Updated description",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)

        body = response.json()

        self.assertTrue(body["ok"])

        self.contributor.refresh_from_db()

        self.assertEqual(self.contributor.contributor_type, "Sponsor")
        self.assertEqual(self.contributor.contributor_name, "Updated Company")
        self.assertEqual(self.contributor.contact_name, "Jordan Jones")
        self.assertEqual(self.contributor.phone, "07123456789")
        self.assertEqual(self.contributor.email, "jordan@example.com")
        self.assertEqual(self.contributor.description, "Updated description")

        history = ContributorHistory.objects.filter(contributor=self.contributor)
        print(history[0].details)



    def test_save_rejects_invalid_email(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("contributors:spreadsheet_save", args=[self.contributor.pk]),
            data=json.dumps(
                {
                    "contributor_type": "Sponsor",
                    "contributor_name": "Acme Ltd",
                    "contact_name": "Alex Smith",
                    "phone": "01234567890",
                    "email": "not-an-email",
                    "description": "Description",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)

        body = response.json()

        self.assertFalse(body["ok"])
        self.assertIn("email", body["errors"])

    def test_save_rejects_blank_company_name(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("contributors:spreadsheet_save", args=[self.contributor.pk]),
            data=json.dumps(
                {
                    "contributor_type": "Sponsor",
                    "contributor_name": "",
                    "contact_name": "Alex Smith",
                    "phone": "01234567890",
                    "email": "alex@example.com",
                    "description": "Description",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)

        body = response.json()

        self.assertFalse(body["ok"])
        self.assertIn("contributor_name", body["errors"])
