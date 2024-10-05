#!/usr/bin/env python
# coding=utf-8
"""
    GarageSale.common.py : 

Summary :
    
    
Use Case :
    
    
Testable Statements :
    ...
"""
import bs4
from django.test import TestCase
from bs4 import BeautifulSoup
from typing import Optional, Union


class TestCaseCommon(TestCase):
    def compare_sets(self, set1: set, set2: set, msg=None):
        """Set comparison function so that it is clear which element is missing from what """

        # Quick check for the same sets
        if set1 == set2:
            return

        extra_set1 = set1.difference(set2)
        extra_set2 = set2.difference(set1)

        # Build a nice message highlight each 'missing' item on a separate line
        if extra_set1 or extra_set2:
            es1 = '\n'.join(map(str, extra_set1))
            es2 = '\n'.join(map(str, extra_set2))

            msg = f'Items in first set missing from second set : {es1}. ' if extra_set1 else ''
            msg += f'Items in second set missing from first set : {es2}. ' if extra_set2 else ''

            raise self.failureException(f'{msg}') from None
        else:
            return

    def setUp(self):
        super().__init__()
        super().addTypeEqualityFunc(set, self.compare_sets)

    def _fetch_elements_by_selector(self, html: str, selector:str) -> set[bs4.Tag]:
        """Return a set Beautifulsoup tags based on the selector
            :param html: the HTML to be searched
            :param selector : The CSS Style selector to be searched for
        """
        soup = BeautifulSoup(html, 'html.parser')
        return set(soup.css.select(selector))

    def assertHTMLHasElements(self, html:Union[str,bytes],
                              selector,
                              msg=""):
        """
        :param html: The HTML to parse
        :param selector: The css selector to apply
        :param msg: The failure message to generate if no HTML matches the selector
        :return:
        """
        selected = self._fetch_elements_by_selector(html, selector)
        if not selected:
            self.fail(msg if msg else f": No html elements matching the given types, names and attributes")

    def assertHTMLMustContainNamed(self, html:Union[str, bytes],
                                    selector:str,
                                   _names:Optional[set[str]]=None,
                                   msg =''):
        """Basic assertion looking for a specific html element with a given optional type and name
            :param html - the html response to be searched
            :param selector - CSS Style Selector
            :param _names - a set of expected 'name', all names must exist within the html
            :param msg_prefix - An application specific message to be pre-pended to any error
        """
        # Build css selectors - types, names and attributes
        # The logic is - element matches any type, and matches any name and matches all attributes
        elements = self._fetch_elements_by_selector(html, selector)

        supplied_names = {element['name'] for element in elements}
        diff = _names - supplied_names
        if diff:
            self.fail(msg if msg else f"No matching elements with the names : {','.join(repr(e) for e in diff)}")


    def assertHTMLElementEquals(self, html, selector, content='', msg=''):
        """Assert that all Elements specified have the expected content
            :param html - the html response to be searched
            :param selector - The CSS Style selector to find
            :param content - the expected content for this element - if multiple elements match the specifiers above
                            then all elements must have the same content
            :param msg - An application specific message to generated on failure"""
        found_elements = self._fetch_elements_by_selector(html, selector=selector)

        if not all(map( lambda item: item['value'] == content, found_elements)):
            self.fail(msg if msg else f"Matching html elements don't have expected content")

