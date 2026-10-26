"""Regression checks for capturing the active page before authentication cleanup."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import SimpleTestCase

from GarageSale.tests.common import IdentifyMixin, SeleniumCommonMixin


class BrowserScreenshotTests(SimpleTestCase):
    def setUp(self):
        # Instantiate the browser helpers without starting a browser or live server.
        class Harness(IdentifyMixin, SeleniumCommonMixin):
            screenshot_sub_directory = 'screenshots'

        self.harness = Harness(methodName='runTest')
        self.harness._screenshot_on_close = True
        self.harness._screenshot_saved_before_logout = False
        browser = self.harness.selenium = Mock()
        browser.current_url = '/communication-templates/'
        browser.save_screenshot.side_effect = lambda path: Path(path).write_text(browser.current_url)
        browser.refresh.side_effect = lambda: setattr(browser, 'current_url', '/user/login/')
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = patch('GarageSale.tests.common.root_screenshot_directory', Path(self.directory.name))
        self.root.start()
        self.addCleanup(self.root.stop)
        self.teardown = patch.object(StaticLiveServerTestCase, 'tearDown')
        self.teardown.start()
        self.addCleanup(self.teardown.stop)

    def screenshot_contents(self):
        files = list(Path(self.directory.name).rglob('*.png'))
        self.assertEqual(len(files), 1)
        return files[0].read_text()

    def test_logout_captures_active_page_and_teardown_does_not_overwrite_it(self):
        self.harness.force_logout()
        self.assertEqual(self.harness.selenium.current_url, '/user/login/')
        self.harness.tearDown()
        self.assertEqual(self.screenshot_contents(), '/communication-templates/')
        self.harness.selenium.save_screenshot.assert_called_once()

    def test_teardown_without_logout_captures_active_page(self):
        self.harness.tearDown()
        self.assertEqual(self.screenshot_contents(), '/communication-templates/')

    def test_disabling_screenshots_still_logs_out(self):
        self.harness._screenshot_on_close = False
        self.harness.force_logout()
        self.harness.tearDown()
        self.harness.selenium.save_screenshot.assert_not_called()
        self.assertEqual(self.harness.selenium.current_url, '/user/login/')

    def test_each_login_session_captures_its_last_active_page(self):
        self.harness.force_logout()
        self.harness.selenium.current_url = '/communication-templates/42/edit/'
        self.harness.force_logout()
        self.harness.tearDown()
        files = list(Path(self.directory.name).rglob('*.png'))
        self.assertTrue(files)
        self.assertIn('/communication-templates/42/edit/', [path.read_text() for path in files])
        self.assertEqual(self.harness.selenium.save_screenshot.call_count, 2)
