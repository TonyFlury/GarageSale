from django.contrib.auth import get_user_model
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.urls import reverse
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.webdriver import WebDriver

from Contributors.models import Contributor


class ContributorSpreadsheetBrowserTests(StaticLiveServerTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.selenium = WebDriver()
        cls.selenium.implicitly_wait(5)

    @classmethod
    def tearDownClass(cls):
        cls.selenium.quit()
        super().tearDownClass()

    def setUp(self):
        User = get_user_model()

        self.user = User.objects.create_user(
            email="admin@example.com",
            password="password123",
            phone="01234567890",
        )

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

        new_row.find_element(By.CSS_SELECTOR, '[name="contributor_type"]').send_keys("Sponsor")
        new_row.find_element(By.CSS_SELECTOR, '[name="contributor_name"]').send_keys("New Company Ltd")
        new_row.find_element(By.CSS_SELECTOR, '[name="contact_name"]').send_keys("Alex Contact")
        new_row.find_element(By.CSS_SELECTOR, '[name="phone"]').send_keys("07123456789")
        new_row.find_element(By.CSS_SELECTOR, '[name="email"]').send_keys("alex@example.com")

        new_row.find_element(By.CSS_SELECTOR, ".save-row").click()

        self.assertTrue(
            Contributor.objects.filter(
                contributor_name="New Company Ltd",
                email="alex@example.com",
            ).exists()
        )

        all_new_rows = self.selenium.find_elements(By.CSS_SELECTOR, "tr.new-row")
        self.assertEqual(len(all_new_rows), 1)

        saved_rows = self.selenium.find_elements(
            By.CSS_SELECTOR,
            'tr[data-contributor-id]:not(.new-row)',
        )

        self.assertGreaterEqual(len(saved_rows), 1)
