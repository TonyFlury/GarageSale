from GarageSale.tests.access_helpers import grant_workflow_permissions
from django.contrib.auth import get_user_model
from django.urls import reverse
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select, WebDriverWait

from Contributors.models import Contributor
from GarageSale.tests.common import SeleniumCommonMixin


class ContributorSpreadsheetBrowserTests(SeleniumCommonMixin):
    def setUp(self):
        super().setUp()
        User = get_user_model()

        self.user = User.objects.create_user(
            email="admin@example.com",
            password="password123",
            phone="01234567890",
            is_verified=True,
        )
        grant_workflow_permissions(self.user)

    def login(self):
        self.client.force_login(self.user)
        cookie = self.client.cookies["sessionid"]

        self.selenium.get(self.live_server_url)

        self.selenium.add_cookie(
            {
                "name": "sessionid",
                "value": cookie.value,
                "path": "/",
            }
        )

    def test_new_row_can_create_contributor_and_add_another_blank_row(self):
        self.login()

        self.selenium.get(
            self.live_server_url + reverse("contributors:spreadsheet")
        )

        new_rows = self.selenium.find_elements(By.CSS_SELECTOR, "tr.new-row")
        self.assertEqual(len(new_rows), 1)

        new_row = new_rows[0]

        self.assertIn("unlocked", new_row.get_attribute("class"))

        Select(new_row.find_element(By.CSS_SELECTOR, '[name="contributor_type"]')).select_by_value("Sponsor")
        new_row.find_element(By.CSS_SELECTOR, '[name="contributor_name"]').send_keys("New Company Ltd")
        new_row.find_element(By.CSS_SELECTOR, '[name="contact_name"]').send_keys("Alex Contact")
        new_row.find_element(By.CSS_SELECTOR, '[name="phone"]').send_keys("07123456789")
        new_row.find_element(By.CSS_SELECTOR, '[name="email"]').send_keys("alex@example.com")

        new_row.find_element(By.CSS_SELECTOR, ".row-status .status").click()

        WebDriverWait(self.selenium, 10).until(lambda driver: driver.find_elements(
            By.CSS_SELECTOR, 'tr[data-contributor-id]:not(.new-row)',
        ))

        self.assertTrue(
            Contributor.objects.filter(
                contributor_name="New Company Ltd",
                email="alex@example.com",
            ).exists()
        )

        all_new_rows = self.selenium.find_elements(By.CSS_SELECTOR, "tr.new-row")
        self.assertEqual(len(all_new_rows), 1)
        self.assertEqual({option.get_attribute("value") for option in Select(
            all_new_rows[0].find_element(By.CSS_SELECTOR, '[name="contributor_type"]'),
        ).options}, {"Sponsor", "Marketer"})
        self.assertEqual(len(all_new_rows[0].find_elements(By.TAG_NAME, "td")),
                         len(self.selenium.find_elements(By.CSS_SELECTOR, "#contributor-sheet thead th")))

        saved_rows = self.selenium.find_elements(
            By.CSS_SELECTOR,
            'tr[data-contributor-id]:not(.new-row)',
        )

        self.assertGreaterEqual(len(saved_rows), 1)
