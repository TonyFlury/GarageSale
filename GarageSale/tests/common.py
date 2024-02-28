#!/usr/bin/env python
# coding=utf-8
"""
    GarageSale.common.py : 

Summary :
    
    
Use Case :
    
    
Testable Statements :
    ...
"""

from django.test import TestCase

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
        super().addTypeEqualityFunc(set, self.compare_sets)