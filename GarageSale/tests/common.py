#!/usr/bin/env python
# coding=utf-8
"""
    GarageSale.common.py : 

Summary :
    
    
Use Case :
    
    
Testable Statements :
    ...
"""
from contextlib import contextmanager
from copy import deepcopy
import datetime
from importlib import import_module
from unittest import TestCase

import bs4
from django.conf import settings
from django.contrib.auth import SESSION_KEY, BACKEND_SESSION_KEY, HASH_SESSION_KEY, get_user_model
from django.contrib.auth.models import AbstractUser
from user_management.models import UserExtended

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from bs4 import BeautifulSoup
from typing import Optional, Union, Any, Type

import selenium
from selenium.common import NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.remote.webdriver import WebDriver as RemoteWebDriver
from selenium.webdriver.support.wait import WebDriverWait

from pathlib import Path

root_screenshot_directory = Path('./testing_screenshots')

if not root_screenshot_directory.exists():
    root_screenshot_directory.mkdir()

import logging

logger = logging.getLogger('django')
logger.setLevel(level=logging.INFO)


class SmartHTMLTestMixins(TestCase):

    def setUp(self):
        super().setUp()

    @staticmethod
    def fetch_elements_by_selector(html: str, selector: str) -> list[bs4.Tag]:
        """Return a set Beautifulsoup tags based on the selector
            :param html: the HTML to be searched
            :param selector : The CSS Style selector to be searched for
        """
        soup = BeautifulSoup(html, 'html.parser')
        return list(soup.css.select(selector))

    def assertHTMLHasElements(self, html: Union[str, bytes],
                              selector,
                              msg=""):
        """
        Success only if the html provided contains the element specified in the selector
            :param html: The HTML to parse
            :param selector: The css selector to apply
            :param msg: The failure message to generate if no HTML matches the selector
            :return:
        """
        selected = self.fetch_elements_by_selector(html, selector)
        if not selected:
            self.fail(msg if msg else f": No html elements matching the given types, names and attributes")

    def assertHTMLMustContainNamed(self, html: Union[str, bytes],
                                   selector: str,
                                   names: Optional[set[str]] = None,
                                   msg=''):
        """Basic assertion looking for a specific html element with a given optional type and name
            :param html - the html response to be searched
            :param selector - CSS Style Selector
            :param names - a set of expected 'name', all names must exist within the html
            :param msg - An application specific message to be pre-pended to any error
        """
        # Build css selectors - types, names and attributes
        # The logic is - element matches any type, and matches any name and matches all attributes
        elements = self.fetch_elements_by_selector(html, selector)

        supplied_names = {element['name'] for element in elements}
        diff = names - supplied_names
        if diff:
            self.fail(msg if msg else f"No matching elements with the names : {','.join(repr(e) for e in diff)}")

    def assertHTMLElementEquals(self, html, selector, content='', msg=''):
        """Assert that all Elements specified have the expected content
            :param html - the html response to be searched
            :param selector - The CSS Style selector to find
            :param content - the expected content for this element - if multiple elements match the specifiers above
                            then all elements must have the same content
            :param msg - An application specific message to generated on failure"""
        found_elements = self.fetch_elements_by_selector(html, selector=selector)

        if not all(map(lambda item: item['value'] == content, found_elements)):
            self.fail(msg if msg else f"Matching html elements don't have expected content")


class SeleniumCommonMixin(StaticLiveServerTestCase):
    """Helper Mixin with some common useful stuff for using Selenium"""
    screenshot_sub_directory = ''

    @classmethod
    def get_driver(cls) -> RemoteWebDriver|None:
        """Can be overriden - by default tests using Firefox browser"""
        return selenium.webdriver.Firefox()

    def get_test_url(self):
        pass

    def screenshot(self, name=None):
        logger.info(f'Taking Screenshot : {name}')
        if self.screen_shot_path:
            test_name = self.id().split('.')[-1]
            self.selenium.save_screenshot(self.screen_shot_path / f'{test_name}_{name if name else ""}.png')

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        if cls.screenshot_sub_directory:
            cls.screen_shot_path = (root_screenshot_directory
                                    / f'{datetime.datetime.utcnow().isoformat(sep="_", timespec="seconds")}' / cls.screenshot_sub_directory)
            cls.screen_shot_path.mkdir(exist_ok=True,parents=True)
        else:
            cls.screen_shot_path = None

        cls.selenium: RemoteWebDriver = cls.get_driver()
        cls.selenium.implicitly_wait(5)

    @property
    def screenshot_on_close(self):
        """Determine if this test generates a screenshot when closing"""
        return self._screenshot_on_close

    @screenshot_on_close.setter
    def screenshot_on_close(self, value):
        """Set True by Default - set False to supress the automated end of test screenshot"""
        self._screenshot_on_close = value

    def setUp(self):
        super().setUp()
        self._screenshot_on_close = True

    def tearDown(self):
        super().tearDown()
        if self.screen_shot_path and self._screenshot_on_close:
            test_name = self.id().split('.')[-1]
            self.selenium.save_screenshot(self.screen_shot_path / f'{test_name}.png')

    @classmethod
    def tearDownClass(cls):
        cls.selenium.quit()

    def _dump_page_source(self, name='', source=''):
        name = name if name else f'{self.id().split(".")[-1]}_dump.html'
        source = source if source else self.selenium.page_source
        with open(name, 'w') as f:
            f.write(source)

    def fill_form(self, url, **kwargs):
        """Selenium fill in forms helper method"""

        logger.info(f'fill_form {url} {kwargs}')
        if url:
            self.selenium.get(url)

        WebDriverWait(self.selenium, 10).until(lambda driver: driver.find_element(By.TAG_NAME,'body'))

        try:
            for field_name, value in kwargs.items():
                try:
                    field = self.selenium.find_element(By.ID, field_name)
                except NoSuchElementException:
                    self._dump_page_source()
                    raise

                if field.tag_name != 'input':
                    raise ValueError(f'{field_name} is not an input element')

                match field.get_attribute('type'):
                    case 'text' | 'email' | 'number' | 'password':
                        field.send_keys(value)
                    case 'checkbox' | 'radio':
                        label = self.selenium.find_element(By.XPATH, f'//label[@for="{field_name}"]')
                        WebDriverWait(self.selenium, 0.5, ).until(EC.element_to_be_clickable(label))
                        if value !=  field.is_selected():
                            label.click()
                    case _:
                        pass
        except:
            raise


class IdentifyMixin(StaticLiveServerTestCase):
    """Simple Helper mixin to identify user via guest or login"""
    selenium: RemoteWebDriver

    def get_test_url(self):
        return NotImplemented

    def force_login(self, user, base_url):
        SessionStore = import_module(settings.SESSION_ENGINE).SessionStore
        base_url = base_url if base_url else self.get_test_url()

        self.selenium.get(base_url)

        session = SessionStore()
        session[SESSION_KEY] = user._meta.pk.value_to_string(user)
        session[BACKEND_SESSION_KEY] = settings.AUTHENTICATION_BACKENDS[0]
        session[HASH_SESSION_KEY] = user.get_session_auth_hash()
        session.save()

        cookie = {
            'name': settings.SESSION_COOKIE_NAME,
            'value': session.session_key,
            'path': '/'
        }
        self.selenium.add_cookie(cookie)
        self.selenium.refresh()

    def force_logout(self):
        self.selenium.delete_cookie(settings.SESSION_COOKIE_NAME)
        self.selenium.refresh()

    @contextmanager
    def identify_as_guest(self, guest_user='test_user@test.com'):
        """Context manager to Authenticate the user as a guest"""
        user_model: Type[UserExtended | AbstractUser] = get_user_model()
        try:
            inst = user_model.objects.get(email=guest_user)
        except user_model.DoesNotExist:
            inst = None

        if inst is None:
            inst = user_model.objects.create_guest_user(guest_user)
        try:
            yield inst
        finally:
            self.force_logout()

    @contextmanager
    def identify_via_login(self, user='test_user@test.com', password=None):
        """Context manager to ensure the user is logged in"""
        user_model: Type[UserExtended | AbstractUser] = get_user_model()
        try:
            inst = user_model.objects.get(email=user)
        except user_model.DoesNotExist:
            inst = None

        if inst is None:
            inst = user_model.objects.create_user(user, password)

        self.force_login(inst, self.get_test_url())
        try:
            yield inst
        finally:
            self.force_logout()


class override_settings_dict:
    """Override a specific setting when it is stored in a dict

      Does not provide a way to delete or add new settings - not required as yet.
    """
    def __init__(self, setting_name:str, keys:list[str]= None, value:Any = None):
        self._setting_name = setting_name
        self._initial_value = getattr(settings, self._setting_name, None)
        new = deepcopy(self._initial_value)
        d = new
        for key in keys[:-1]:
            d = d[key]
        d[keys[-1]] = value
        self._new = new

    def __enter__(self):
        # Set the new setting attribute
        setattr(settings, self._setting_name, self._new)

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Set the setting back to the original
        setattr(settings, self._setting_name, self._initial_value)
