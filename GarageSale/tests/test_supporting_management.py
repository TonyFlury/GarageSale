"""Supported charity management and event selection/order regression coverage."""
from datetime import date
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
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

    def test_directory_search_is_paginated_and_excludes_selected_organisations(self):
        Supporting.objects.bulk_create([
            Supporting(name=f"Directory charity {index:03}", website="https://example.com")
            for index in range(45)
        ])
        url = reverse("TeamPages:SupportingSearch")
        first_page = self.client.get(url).json()
        self.assertEqual((len(first_page["results"]), first_page["count"], first_page["pages"]), (20, 48, 3))
        second_page = self.client.get(url, {"page": 2}).json()
        self.assertFalse({row["id"] for row in first_page["results"]} & {row["id"] for row in second_page["results"]})
        response = self.client.get(url, {"q": "FIRST", "selected": [self.first.pk]}).json()
        self.assertEqual(response["results"], [])
        response = self.client.get(url, {"q": "FIRST", "selected": ["invalid"]}).json()
        self.assertEqual(response["results"], [{"id": self.first.pk, "name": self.first.name}])
        self.client.force_login(get_user_model().objects.create_user("no-directory@example.com", "password"))
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_event_form_renders_only_selected_charities_and_keeps_submitted_order_after_error(self):
        event = EventData.objects.create(event_date=date(2027, 6, 1), use_from=date(2027, 1, 1))
        event.supporting_organisations.add(self.first)
        response = self.client.get(reverse("TeamPages:EventEdit", args=[event.pk]))
        self.assertContains(response, self.first.name)
        self.assertNotContains(response, self.unselected.name)
        data = event_data([self.second, self.first])
        data["event_date"] = "invalid"
        response = self.client.post(reverse("TeamPages:EventEdit", args=[event.pk]), data)
        choices = list(response.context["form"].fields["supporting_organisations"].choices)
        self.assertEqual(choices, [(self.second.pk, self.second.name), (self.first.pk, self.first.name)])

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
    screenshot_sub_directory = "SupportedCharities"

    def setUp(self):
        super().setUp()
        self.selenium.set_window_size(1440, 1100)

    def drag_charity(self, source, target, before=False):
        # HTML5 drag events avoid Selenium pointer/scroll timing failures while
        # exercising the real browser handlers and DataTransfer contract.
        self.selenium.execute_script("""
            const [source, target, before] = arguments;
            const handle = source.querySelector('.supporting-drag-handle');
            const transfer = new DataTransfer();
            const bounds = target.getBoundingClientRect();
            const options = {bubbles: true, cancelable: true, dataTransfer: transfer,
                clientX: bounds.left + bounds.width / 2,
                clientY: before ? bounds.top + 5 : bounds.bottom - 5};
            if (!handle.dispatchEvent(new DragEvent('dragstart', options)))
                throw new Error('Charity drag was rejected');
            if (target.dispatchEvent(new DragEvent('dragover', options)))
                throw new Error('Charity drop target did not accept the drag');
            target.dispatchEvent(new DragEvent('drop', options));
            handle.dispatchEvent(new DragEvent('dragend', options));
        """, source, target, before)

    def test_drag_into_empty_selection_and_back_without_saving(self):
        user = get_user_model().objects.create_user("empty-selection@example.com", "password", is_verified=True)
        grant_workflow_permissions(user)
        charity = Supporting.objects.create(name="Only charity", website="https://example.com")
        url = self.live_server_url + reverse("TeamPages:EventCreate")
        self.force_login(user, url)
        self.selenium.get(url)
        wait = WebDriverWait(self.selenium, 10)
        wait.until(lambda driver: len(driver.find_elements(By.CSS_SELECTOR, "[data-results] li")) == 1)
        source = self.selenium.find_element(By.CSS_SELECTOR, "[data-results] li")
        destination = self.selenium.find_element(By.CSS_SELECTOR, '[data-drop-zone="selected"] h3')
        self.drag_charity(source, destination)
        rows = self.selenium.find_elements(By.CSS_SELECTOR, "[data-selected] li")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].find_element(By.CSS_SELECTOR, 'input[type="hidden"]').get_attribute("value"), str(charity.pk))
        self.drag_charity(rows[0], self.selenium.find_element(By.CSS_SELECTOR, '[data-drop-zone="available"] h3'))
        wait.until(lambda driver: len(driver.find_elements(By.CSS_SELECTOR, "[data-results] li")) == 1)
        self.assertFalse(self.selenium.find_elements(By.CSS_SELECTOR, "[data-selected] li"))
        self.assertFalse(self.selenium.find_elements(By.CSS_SELECTOR, ".supporting-drop-marker, .is-dragging, .is-drop-target"))
        self.assertFalse(EventData.objects.exists())
        self.assertTrue(Supporting.objects.filter(pk=charity.pk).exists())

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
        rows = self.selenium.find_elements(By.CSS_SELECTOR, "[data-selected] li")
        self.assertEqual(len(rows), 2, self.selenium.page_source)
        rows[1].find_element(By.CSS_SELECTOR, '[data-move="up"]').click()
        self.assertIn("Second charity", self.selenium.find_elements(By.CSS_SELECTOR, "[data-selected] li")[0].text)
        rows = self.selenium.find_elements(By.CSS_SELECTOR, "[data-selected] li")
        self.drag_charity(rows[0], rows[1])
        self.assertIn("First charity", self.selenium.find_elements(By.CSS_SELECTOR, "[data-selected] li")[0].text)
        rows = self.selenium.find_elements(By.CSS_SELECTOR, "[data-selected] li")
        self.drag_charity(rows[1], rows[0], before=True)
        self.assertIn("Second charity", self.selenium.find_elements(By.CSS_SELECTOR, "[data-selected] li")[0].text)
        self.assertFalse(self.selenium.find_elements(By.CSS_SELECTOR, ".supporting-drop-marker, .is-dragging"))
        self.selenium.find_element(By.CSS_SELECTOR, 'button[type="submit"]').click()
        WebDriverWait(self.selenium, 10).until(lambda driver: driver.current_url.endswith(reverse("TeamPages:EventList")))
        self.assertEqual(list(event.supporting_organisations.order_by("index", "pk")), [second, first])
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual((second.index, first.index), (1, 2))

    def test_large_directory_search_add_remove_and_direct_position_save(self):
        user = get_user_model().objects.create_user("large-order@example.com", "password", is_verified=True)
        grant_workflow_permissions(user)
        charities = Supporting.objects.bulk_create([
            Supporting(name=f"Directory charity {index:03}", website="https://example.com")
            for index in range(62)
        ])
        target = Supporting.objects.create(name="Target charity", website="https://target.example.com")
        event = EventData.objects.create(event_date=date(2027, 6, 1), use_from=date(2027, 1, 1),
                                         open_billboard_bookings=date(2027, 2, 1), close_billboard_bookings=date(2027, 5, 1),
                                         open_sales_bookings=date(2027, 3, 1), close_sales_bookings=date(2027, 5, 30))
        event.supporting_organisations.add(*charities[:2])
        url = self.live_server_url + reverse("TeamPages:EventEdit", args=[event.pk])
        self.force_login(user, url)
        self.selenium.get(url)
        self.selenium.set_window_size(1440, 1100)
        wait = WebDriverWait(self.selenium, 10)
        wait.until(lambda driver: len(driver.find_elements(By.CSS_SELECTOR, "[data-results] li")) == 20)
        self.assertEqual(len(self.selenium.find_elements(By.CSS_SELECTOR, "[data-selected] li")), 2)
        self.selenium.find_element(By.CSS_SELECTOR, '[data-page="next"]').click()
        wait.until(lambda driver: driver.find_element(By.CSS_SELECTOR, "[data-page-label]").text == "Page 2 of 4")
        self.selenium.find_element(By.CSS_SELECTOR, "[data-search]").send_keys("Target")
        add = wait.until(lambda driver: driver.find_element(By.CSS_SELECTOR, 'button[aria-label="Add Target charity"]'))
        add.click()
        target_row = self.selenium.find_element(By.CSS_SELECTOR, f'[data-selected] li[data-charity-id="{target.pk}"]')
        position = target_row.find_element(By.CSS_SELECTOR, "[data-position]")
        position.send_keys(Keys.CONTROL, "a")
        position.send_keys("1", Keys.ENTER)
        self.assertIn("Target charity", self.selenium.find_elements(By.CSS_SELECTOR, "[data-selected] li")[0].text)
        self.selenium.find_element(By.CSS_SELECTOR, 'button[aria-label="Remove Directory charity 000"]').click()
        self.assertEqual(len(self.selenium.find_elements(By.CSS_SELECTOR, "[data-selected] li")), 2)
        target_row = self.selenium.find_element(By.CSS_SELECTOR, f'[data-selected] li[data-charity-id="{target.pk}"]')
        available_zone = self.selenium.find_element(By.CSS_SELECTOR, '[data-drop-zone="available"] h3')
        self.drag_charity(target_row, available_zone)
        wait.until(lambda driver: driver.find_elements(By.CSS_SELECTOR, f'[data-results] li[data-charity-id="{target.pk}"]'))
        self.assertEqual(len(self.selenium.find_elements(By.CSS_SELECTOR, "[data-selected] li")), 1)
        # Removing an organisation from the event does not delete the organisation.
        self.assertTrue(Supporting.objects.filter(pk=target.pk).exists())
        available_row = self.selenium.find_element(By.CSS_SELECTOR, f'[data-results] li[data-charity-id="{target.pk}"]')
        selected_row = self.selenium.find_element(By.CSS_SELECTOR, "[data-selected] li")
        self.drag_charity(available_row, selected_row, before=True)
        self.assertEqual(len(self.selenium.find_elements(By.CSS_SELECTOR, "[data-selected] li")), 2)
        self.assertIn("Target charity", self.selenium.find_elements(By.CSS_SELECTOR, "[data-selected] li")[0].text)
        self.assertEqual(list(event.supporting_organisations.order_by("pk")), charities[:2])
        rows = self.selenium.find_elements(By.CSS_SELECTOR, "[data-selected] li")
        self.drag_charity(rows[0], rows[1])
        self.assertIn("Directory charity 001", self.selenium.find_elements(By.CSS_SELECTOR, "[data-selected] li")[0].text)
        self.screenshot("search-and-selected-charities")
        self.selenium.find_element(By.CSS_SELECTOR, 'button[type="submit"]').click()
        wait.until(lambda driver: driver.current_url.endswith(reverse("TeamPages:EventList")))
        self.assertEqual(list(event.supporting_organisations.order_by("index", "pk")), [charities[1], target])
