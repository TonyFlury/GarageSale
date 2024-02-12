#!/usr/bin/env python
# coding=utf-8
import dataclasses
from dataclasses import asdict
from django.test import testcases

from ..middleware.pageVisits import CachedDeque, PageVisit

import unittest
from unittest import mock
from django.db import models
import time


# ToDo - simplify basic testing - we don't need a mobel - just something that supports bulk_create


@unittest.skip('Caching system not being used')
class Test_CacheOperations(unittest.TestCase):
    def setUp(self):
        class TempModel(models.Model):
            """Temp Model for testing"""
            one = models.IntegerField()
            two = models.IntegerField()
            three = models.IntegerField()

        class TempInstance(TempModel):
            """Instance of the TempModel call in order to fool mock library to not create mocks for each attribute"""
            one = 0
            two = 0
            three = 0

        self.mock_model = mock.create_autospec(spec=TempInstance, spec_set=True)

    def test_0900_test_cache_creation(self):
        """Check that the cache model can be created"""
        cache = CachedDeque(self.mock_model, max_length=20, timeout=30)
        self.assertEqual(cache.model, self.mock_model)
        self.assertTrue(cache.max_length >= 20)
        self.assertEqual(cache.timeout, 30)
        self.assertTrue(cache.maxlen >= 20)  # test parent class cache

    def test_0910_test_cache_insertion(self):
        """Check records are inserted into the cache
            timeout set to one day for testing purposes
        """
        cache = CachedDeque(self.mock_model, max_length=20, timeout=24 * 60 * 60)
        cache.append({'one': 1, 'two': 2, 'three': 3})

        self.assertEqual(len(cache), 1)
        self.assertEqual(cache[0], {'one': 1, 'two': 2, 'three': 3})

    def test_0920_test_bulk_insert_no_timeout(self):
        """Check that the cache does a bulk create when the cache becomes full"""
        @dataclasses.dataclass
        class entry:
            one: int
            two: int
            three: int

        d = [entry(**{'one':i*10+i, 'two': i*10+2, 'three':i*10+3}) for i in range(5)]

        cache = CachedDeque(self.mock_model, max_length=5, timeout=24 * 60 * 60)
        for item in d:
            cache.append(item)

        # Added 5 items - cache should be full but not written
        self.assertEqual(len(cache),5)
        self.mock_model.objects.bulk_create.assert_not_called()

        # Add another item
        d.append(entry(**{'one': 51, 'two': 52, 'three': 53}))
        cache.append( d )

        self.mock_model.objects.bulk_create.assert_called_with(
            [ self.mock_model(asdict(i)) for i in d[0:5]]
        )

        self.assertEqual(len(cache),1)

    def test_0930_test_bulk_insert_timeout(self):

        @dataclasses.dataclass
        class entry:
            one: int
            two: int
            three: int

        d = [entry(**{'one':i*10+i, 'two': i*10+2, 'three':i*10+3}) for i in range(5)]

        cache = CachedDeque(self.mock_model, max_length=10, timeout=10)
        for item in d:
            cache.append(item)
        self.mock_model.objects.bulk_create.assert_not_called()

        time.sleep(11) # sleep for 11 seconds to ensure the timeout works

        self.mock_model.objects.bulk_create.assert_called_with(
            [ self.mock_model(asdict(i)) for i in d[0:5]]
        )

        self.assertEqual(len(cache),0)
