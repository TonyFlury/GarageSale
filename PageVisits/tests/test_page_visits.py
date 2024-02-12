#!/usr/bin/env python
# coding=utf-8
"""
    GarageSale.test_page_visits.py : 

Summary :
    
    
Use Case :
    
    
Testable Statements :
    ...
"""
import datetime

from django import test
from time import sleep
from ..models import  PageVisit
from django.contrib.auth.models import User


def assertBetween(self: test.TestCase, value, min, max, msg=''):
    if value < min:
        self.fail(msg if msg else f'{value} < {min}')
    if value > max:
        self.fail(msg if msg else f'{value} > {max}')


test.TestCase.assertBetween = assertBetween


class Test_PageVisits(test.TestCase):
    def setUp(self):
        pass

    @staticmethod
    def naive( ts ):
        return False if (ts.tzinfo is not None and ts.tzinfo.utcoffset(ts) is not None) else True

    def test_1000_single_visit(self):
        """Single page fetch with no user logged in"""
        self.assertEqual(len(PageVisit.objects.all()), 0)
        before = datetime.datetime.now(datetime.timezone.utc)
        c = test.Client()
        response = c.get('/')
        after = datetime.datetime.now(datetime.timezone.utc)
        self.assertEqual(len(PageVisit.objects.all()), 1)

        inst:PageVisit = PageVisit.objects.get()

        self.assertBetween(inst.timestamp, before, after)
        self.assertEqual( (inst.sourceIP, inst.path, inst.method,inst.response_code, inst.username ),
                          ('127.0.0.1', '/', 'GET', response.status_code, ''))

    def test_1010_single_visit_signedin(self):
        """"Single Page fetch with signed in user"""
        u = User.objects.create_user(username='user1')
        before = datetime.datetime.now(datetime.timezone.utc)
        c = test.Client()
        c.force_login(u)
        response = c.get('/')
        after = datetime.datetime.now(datetime.timezone.utc)
        self.assertEqual(len(PageVisit.objects.all()), 1)

        inst:PageVisit = PageVisit.objects.get()

        self.assertBetween(inst.timestamp, before, after)
        self.assertEqual( (inst.sourceIP, inst.path, inst.method,inst.response_code, inst.username ),
                          ('127.0.0.1', '/', 'GET', response.status_code, u.username))

    def test_1020_single_POST(self):
        """Single visit with a POST request"""
        u = User.objects.create_user(username='user1')
        before = datetime.datetime.now(datetime.timezone.utc)
        c = test.Client()
        c.force_login(u)
        response = c.post('/')
        after = datetime.datetime.now(datetime.timezone.utc)
        self.assertEqual(len(PageVisit.objects.all()), 1)

        inst:PageVisit = PageVisit.objects.get()

        self.assertBetween(inst.timestamp, before, after)
        self.assertEqual( (inst.sourceIP, inst.path, inst.method,inst.response_code, inst.username ),
                          ('127.0.0.1', '/', 'POST', response.status_code, u.username))

    def test_1030_get_404(self):
        """A get for page which will cause a 404"""
        u = User.objects.create_user(username='user1')
        before = datetime.datetime.now(datetime.timezone.utc)
        c = test.Client()
        c.force_login(u)
        response = c.post('/rubbish')
        after = datetime.datetime.now(datetime.timezone.utc)
        self.assertEqual(len(PageVisit.objects.all()), 1)
        self.assertEqual(response.status_code, 404)

        inst: PageVisit = PageVisit.objects.get()

        self.assertBetween(inst.timestamp, before, after)
        self.assertEqual((inst.sourceIP, inst.path, inst.method, inst.response_code, inst.username),
                         ('127.0.0.1', '/rubbish', 'POST', response.status_code, u.username))

    def test_1100_multiple_gets(self):
        """A get for page which will cause a 404"""
        u = User.objects.create_user(username='user1')
        before = datetime.datetime.now(datetime.timezone.utc)
        c = test.Client()
        resp1 = c.post('/rubbish')
        c.force_login(u)
        resp2 = c.get('/')
        after = datetime.datetime.now(datetime.timezone.utc)
        self.assertEqual(len(PageVisit.objects.all()), 2)

        times = PageVisit.objects.values_list('timestamp', flat=True ).order_by('timestamp')
        for time in times:
            self.assertBetween(time, before, after)

        data = PageVisit.objects.values_list('sourceIP','path','method', 'response_code', 'username').order_by('timestamp')
        self.assertEqual( [ item for item in data],
                            [('127.0.0.1', '/rubbish', 'POST', 404, '' ),
                             ('127.0.0.1', '/', 'GET', 200, 'user1')
                          ] )


