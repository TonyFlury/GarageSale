from datetime import timedelta
from decimal import Decimal
from importlib import import_module
from types import SimpleNamespace

from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import connection
from django.test import RequestFactory, TestCase
from django.template.loader import render_to_string
from django.utils import timezone
from django.urls import reverse

from Contributors.models import Contributor, ContributorEvent, Contributions
from GarageSale.models import EventData
from Sponsors.public_sponsors import sponsor_wall_for_event
from Sponsors.views import SponsorSpreadsheetView


class SponsorContributionValueTests(TestCase):
    def setUp(self):
        today = timezone.localdate()
        self.event = EventData.objects.create(event_date=today + timedelta(days=30), use_from=today - timedelta(days=1))
        self.sponsors = [Contributor.objects.create(contributor_type='Sponsor', contributor_name=f'Sponsor {i}') for i in range(6)]
        ContributorEvent.objects.bulk_create([
            ContributorEvent(contributor=sponsor, event=self.event, status='Confirmed') for sponsor in self.sponsors
        ])

    def contribution(self, index, **values):
        return Contributions.objects.create(contributor=self.sponsors[index], event=self.event, **values)

    def test_model_validation_matches_cash_and_gift_requirements(self):
        Contributions(cash=True, amount=Decimal('10')).clean()
        Contributions(gift='Donated equipment').clean()
        for contribution, field in [(Contributions(cash=True), 'amount'),
                                    (Contributions(cash=True, amount=0), 'amount'),
                                    (Contributions(gift=' ', amount=10), 'gift')]:
            with self.subTest(field=field):
                with self.assertRaises(ValidationError) as error:
                    contribution.clean()
                self.assertIn(field, error.exception.message_dict)

    def test_cash_and_gift_values_combine_for_event_headliners(self):
        for i in range(4):
            self.contribution(i, cash=True, amount=100 + i, gift='Cash sponsorship')
        self.contribution(4, gift='Equipment', amount=Decimal('150.50'))
        self.contribution(4, cash=True, amount=Decimal('25.50'))
        self.contribution(5, gift='Unknown-value gift')
        wall = sponsor_wall_for_event(self.event)
        self.assertEqual({item.pk for item in wall if item.wall_headliner},
                         {self.sponsors[i].pk for i in (1, 2, 3, 4)})
        self.assertFalse(any(hasattr(item, 'amount') for item in wall))

    def test_values_are_scoped_to_confirmed_sponsors_and_event(self):
        other_event = EventData.objects.create(event_date=self.event.event_date + timedelta(days=365), use_from=self.event.use_from)
        self.contribution(0, gift='Gift', amount=10)
        Contributions.objects.create(contributor=self.sponsors[1], event=other_event, gift='Other event', amount=5000)
        self.contribution(2, gift='Unconfirmed gift', amount=9000)
        ContributorEvent.objects.create(contributor=self.sponsors[2], event=self.event, status='Declined')
        wall = sponsor_wall_for_event(self.event)
        self.assertNotIn(self.sponsors[2].pk, [item.pk for item in wall])
        self.assertEqual([item.pk for item in wall if item.wall_headliner], [self.sponsors[0].pk])

    def test_unvalued_gift_description_is_not_interpreted_as_money(self):
        self.contribution(0, gift='5000')
        self.contribution(1, gift='A gift', amount=0)
        self.assertFalse(any(item.wall_headliner for item in sponsor_wall_for_event(self.event)))

    def test_cash_email_totals_use_numeric_amount_and_exclude_valued_gifts(self):
        self.contribution(0, cash=True, amount=Decimal('25.50'), gift='A cash donation')
        self.contribution(0, cash=True, gift='£24.50')
        self.contribution(0, gift='Equipment', amount=5000)
        sponsor = self.sponsors[0]
        sponsor.sponsor_status = 'Confirmed'
        request = RequestFactory().get('/')
        request.current_event = self.event
        view = SponsorSpreadsheetView()
        if not hasattr(request, "user"):
            request.user = SimpleNamespace(is_authenticated=True, is_active=True, has_perm=lambda permission: True)
        view.setup(request)
        self.assertEqual(view._cash_donations([sponsor], self.event), {sponsor.pk: '£50'})

    def test_internal_lists_show_amount_and_description_without_public_values(self):
        cash = self.contribution(0, cash=True, amount=Decimal('50.25'), gift='Thank you')
        gift = self.contribution(0, gift='A <hamper>', amount=Decimal('250'))
        for template in ('contributor_contributions.html', 'Sponsors/widgets/contributions.html'):
            html = render_to_string(template, {'contributor': self.sponsors[0], 'current_event': self.event,
                                              'contributions': [cash, gift], 'show_contributions': True})
            self.assertIn('£50.25', html)
            self.assertIn('Thank you', html)
            self.assertIn('A &lt;hamper&gt;', html)
            self.assertIn('estimated value £250.00', html)
        response = self.client.get(reverse('sponsors:sponsor_list'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, '£250')
        self.assertNotContains(response, '£50.25')

    def test_data_migration_converts_valid_cash_and_keeps_unvalued_gifts(self):
        cash = self.contribution(0, cash=True, gift='£1,250.50')
        gift = self.contribution(1, gift='£500 voucher')
        invalid = self.contribution(2, cash=True, gift='Unknown')
        too_precise = self.contribution(3, cash=True, gift='1.234')
        too_large = self.contribution(4, cash=True, gift='10000000000')
        migration = import_module('Contributors.migrations.0006_contribution_amount')
        migration.migrate_cash_amounts(apps, SimpleNamespace(connection=connection))
        cash.refresh_from_db()
        self.assertEqual(cash.amount, Decimal('1250.50'))
        self.assertEqual(cash.gift, '')
        for item in (gift, invalid, too_precise, too_large):
            original = item.gift
            item.refresh_from_db()
            self.assertIsNone(item.amount)
            self.assertEqual(item.gift, original)
        migration.migrate_cash_amounts(apps, SimpleNamespace(connection=connection))
        cash.refresh_from_db()
        self.assertEqual(cash.amount, Decimal('1250.50'))
        migration.restore_cash_text(apps, SimpleNamespace(connection=connection))
        cash.refresh_from_db()
        self.assertEqual(cash.gift, '£1250.50')
