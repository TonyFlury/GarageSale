"""Supported charity management and event selection/order regression coverage."""
from datetime import date
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from GarageSale.models import EventData, Supporting
from GarageSale.tests.access_helpers import grant_workflow_permissions
from GarageSale.tests.common import IdentifyMixin, SeleniumCommonMixin


def event_data(organisations=()):
    return {
        "event_date": "2027-06-01", "use_from": "2027-01-01",
        "open_billboard_bookings": "2027-02-01", "close_billboard_bookings": "2027-05-01",
        "open_sales_bookings": "2027-03-01", "close_sales_bookings": "2027-05-30",
        "supporting_organisations": [str(item.pk) for item in organisations],
        "myGoogleMapURL": "https://example.com/map",
    }


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class SupportingManagementTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("charities@example.com", "password")
        grant_workflow_permissions(self.user)
        self.client.force_login(self.user)
        self.first = Supporting.objects.create(name="First charity", website="https://first.example.com", index=4)
        self.second = Supporting.objects.create(name="Second charity", website="https://second.example.com", index=8)
        self.unselected = Supporting.objects.create(name="Unselected", website="https://other.example.com", index=50)

    def test_list_details_and_blank_creation_page(self):
        self.assertContains(self.client.get(reverse("TeamPages:Root")), "Supported charities")
        response = self.client.get(reverse("TeamPages:SupportingList"))
        self.assertContains(response, "Support New Charity")
        self.assertContains(response, reverse("TeamPages:SupportingDetail", args=[self.first.pk]))
        self.assertContains(self.client.get(reverse("TeamPages:SupportingDetail", args=[self.first.pk])), self.first.website)
        form = self.client.get(reverse("TeamPages:SupportingCreate")).context["form"]
        self.assertFalse(form.is_bound)
        self.assertIsNone(form.instance.pk)
        self.assertNotIn("index", form.fields)

    def test_create_ignores_submitted_index_and_saves_upload(self):
        with TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory):
            response = self.client.post(reverse("TeamPages:SupportingCreate"), {
                "name": "New charity", "website": "https://new.example.com", "index": "1",
                "logo": SimpleUploadedFile("logo.svg", b'<svg xmlns="http://www.w3.org/2000/svg"/>', content_type="image/svg+xml"),
            })
            charity = Supporting.objects.get(name="New charity")
            self.assertRedirects(response, reverse("TeamPages:SupportingDetail", args=[charity.pk]))
            self.assertEqual(charity.index, 100)
            self.assertTrue(charity.logo.storage.exists(charity.logo.name))
            response = self.client.post(reverse("TeamPages:SupportingEdit", args=[charity.pk]), {
                "name": "Renamed charity", "website": charity.website, "index": "2",
            })
            self.assertEqual(response.status_code, 302)
            charity.refresh_from_db()
            self.assertEqual(charity.index, 100)
            self.assertTrue(charity.logo)
            self.assertEqual(charity.name, "Renamed charity")

    def test_invalid_charity_does_not_save(self):
        response = self.client.post(reverse("TeamPages:SupportingCreate"), {"name": "Invalid", "website": "invalid"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        self.assertFalse(Supporting.objects.filter(name="Invalid").exists())

    def test_create_and_edit_event_save_selection_and_order(self):
        response = self.client.post(reverse("TeamPages:EventCreate"), event_data([self.second, self.first]))
        self.assertEqual(response.status_code, 302, response.context["form"].errors if response.status_code == 200 else "")
        self.assertRedirects(response, reverse("TeamPages:EventList"))
        event = EventData.objects.get()
        self.assertEqual(list(event.supporting_organisations.order_by("index", "pk")), [self.second, self.first])
        self.second.refresh_from_db()
        self.first.refresh_from_db()
        self.assertEqual((self.second.index, self.first.index), (1, 2))
        response = self.client.get(reverse("TeamPages:EventEdit", args=[event.pk]))
        self.assertEqual(response.context["form"].instance, event)
        self.assertContains(response, 'name="supporting_organisations"')
        self.assertContains(response, "shared by all events")
        response = self.client.post(reverse("TeamPages:EventEdit", args=[event.pk]), event_data([self.first]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(list(event.supporting_organisations.all()), [self.first])
        self.unselected.refresh_from_db()
        self.assertEqual(self.unselected.index, 50)
        self.client.post(reverse("TeamPages:EventEdit", args=[event.pk]), event_data())
        self.assertFalse(event.supporting_organisations.exists())

    def test_invalid_event_does_not_change_existing_selection_or_indexes(self):
        event = EventData.objects.create(event_date=date(2027, 6, 1), use_from=date(2027, 1, 1))
        event.supporting_organisations.add(self.first)
        data = event_data([self.second])
        data["event_date"] = "invalid"
        response = self.client.post(reverse("TeamPages:EventEdit", args=[event.pk]), data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(event.supporting_organisations.all()), [self.first])
        self.second.refresh_from_db()
        self.assertEqual(self.second.index, 8)
        data = event_data()
        data["supporting_organisations"] = ["999999"]
        self.assertTrue(self.client.post(reverse("TeamPages:EventCreate"), data).context["form"].errors)
        self.assertEqual(EventData.objects.count(), 1)

    def test_viewer_cannot_change_charities_or_events(self):
        viewer = get_user_model().objects.create_user("viewer@example.com", "password")
        viewer.user_permissions.add(*Permission.objects.filter(
            content_type__app_label="GarageSale", codename__in=["view_supporting", "view_eventdata"],
        ))
        self.client.force_login(viewer)
        self.assertEqual(self.client.get(reverse("TeamPages:SupportingList")).status_code, 200)
        self.assertNotContains(self.client.get(reverse("TeamPages:SupportingDetail", args=[self.first.pk])), "Edit charity")
        for url in [reverse("TeamPages:SupportingCreate"), reverse("TeamPages:SupportingEdit", args=[self.first.pk]), reverse("TeamPages:EventCreate")]:
            self.assertEqual(self.client.get(url).status_code, 403)
            self.assertEqual(self.client.post(url, {}).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(reverse("TeamPages:SupportingList")).status_code, 302)


@override_settings(TEST_SERVER=False)
class SupportingOrderBrowserTests(IdentifyMixin, SeleniumCommonMixin):
    def test_event_editor_moves_selected_charities_and_saves_their_indexes(self):
        user = get_user_model().objects.create_user("order@example.com", "password", is_verified=True)
        grant_workflow_permissions(user)
        first = Supporting.objects.create(name="First charity", website="https://first.example.com", index=1)
        second = Supporting.objects.create(name="Second charity", website="https://second.example.com", index=2)
        event = EventData.objects.create(event_date=date(2027, 6, 1), use_from=date(2027, 1, 1),
                                         open_billboard_bookings=date(2027, 2, 1), close_billboard_bookings=date(2027, 5, 1),
                                         open_sales_bookings=date(2027, 3, 1), close_sales_bookings=date(2027, 5, 30))
        event.supporting_organisations.add(first, second)
        self.force_login(user, self.live_server_url + reverse("TeamPages:EventEdit", args=[event.pk]))
        self.selenium.get(self.live_server_url + reverse("TeamPages:EventEdit", args=[event.pk]))
        rows = self.selenium.find_elements(By.CSS_SELECTOR, ".supporting-picker li")
        self.assertEqual(len(rows), 2, self.selenium.page_source)
        rows[1].find_element(By.CSS_SELECTOR, '[data-move="up"]').click()
        self.assertIn("Second charity", self.selenium.find_elements(By.CSS_SELECTOR, ".supporting-picker li")[0].text)
        self.selenium.find_element(By.CSS_SELECTOR, 'button[type="submit"]').click()
        WebDriverWait(self.selenium, 10).until(lambda driver: driver.current_url.endswith(reverse("TeamPages:EventList")))
        self.assertEqual(list(event.supporting_organisations.order_by("index", "pk")), [second, first])
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual((second.index, first.index), (1, 2))
