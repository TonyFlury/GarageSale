import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils.text import slugify

from .__common import TestMigrations


class BaseMigrationTests(TestMigrations):
    migrate_from = [
        ('CraftMarket', '0011_alter_marketer_options'),
        ('Sponsors', '0002_alter_sponsor_options'),
        ('Contributors', None),
    ]
    migrate_to = [('Contributors', '0001_initial')]

    def setUp(self):
        media = TemporaryDirectory()
        self.addCleanup(media.cleanup)
        media_settings = override_settings(MEDIA_ROOT=media.name)
        media_settings.enable()
        self.addCleanup(media_settings.disable)
        super().setUp()

    def setUpBeforeMigration(self, apps):
        self.EventData = apps.get_model('GarageSale', 'EventData')
        self.Marketer = apps.get_model('CraftMarket', 'Marketer')
        self.History = apps.get_model('CraftMarket', 'History')
        self.Sponsor = apps.get_model('Sponsors', 'Sponsor')
        self.seed_records()

    def setUpAfterMigration(self, apps):
        self.Contributor = apps.get_model('Contributors', 'Contributor')
        self.ContributorHistory = apps.get_model('Contributors', 'ContributorHistory')
        self.ContributorEvent = apps.get_model('Contributors', 'ContributorEvent')
        self.Contributions = apps.get_model('Contributors', 'Contributions')

    def clear_source_data(self, apps):
        # A normal flush may not discover tables without live model definitions.
        apps.get_model('CraftMarket', 'History').objects.all().delete()
        apps.get_model('CraftMarket', 'Marketer').objects.all().delete()
        apps.get_model('Sponsors', 'Sponsor').objects.all().delete()

    def seed_records(self):
        pass

    def create_event(self, year):
        return self.EventData.objects.create(
            event_date=datetime.date(year, 6, 20), use_from=datetime.date(year, 6, 19),
        )

    def create_marketer(self, event, name='B&M wood working', contact='Bary Wood', states=('IN', 'CO')):
        marketer = self.Marketer.objects.create(
            event_id=event.pk, trading_name=name, contact_name=contact,
            email=f'{slugify(name)}@marketer.example.com',
        )
        origin = datetime.datetime.combine(event.event_date, datetime.time.min, tzinfo=datetime.UTC)
        for state in ('NW', *states):
            history = self.History.objects.create(marketeer_id=marketer.pk, state=state)
            days_before = {'NW': 30, 'IN': 29, 'CO': 25, 'RE': 25}[state]
            # Historical managers/save methods do not create or date history.
            self.History.objects.filter(pk=history.pk).update(timestamp=origin - datetime.timedelta(days=days_before))
        return marketer

    def create_sponsor(self, event, name='Sponsor1', confirmed=False, gift=None, logo=b'logo'):
        sponsor = self.Sponsor.objects.create(
            event_id=event.pk, company_name=name, email=f'{slugify(name)}@sponsor.example.com',
            description=f'Sponsor for {event.event_date.year}', confirmed=confirmed, gift=gift,
            logo=SimpleUploadedFile('logo.jpg', logo, content_type='image/jpeg') if logo is not None else '',
        )
        timestamp = datetime.datetime.combine(event.event_date, datetime.time.min, tzinfo=datetime.UTC) - datetime.timedelta(days=30)
        self.Sponsor.objects.filter(pk=sponsor.pk).update(creation_date=timestamp)
        sponsor.refresh_from_db()
        return sponsor

    def check_marketer(self, contributor, records):
        matching = [record for record in records if record.trading_name == contributor.contributor_name]
        latest = max(matching, key=lambda record: record.event.event_date)
        self.assertEqual((contributor.contributor_type, contributor.email, contributor.contact_name),
                         ('Marketer', latest.email, latest.contact_name))
        expected = self.History.objects.filter(marketeer_id__in=[record.pk for record in matching])
        created_at = expected.filter(state='NW').order_by('timestamp').first().timestamp
        self.assertEqual(self.ContributorHistory.objects.get(contributor_id=contributor.pk, event_type='Create').timestamp, created_at)
        expected_events = sorted(
            (row.marketeer.event_id, {'IN': 'Invited', 'CO': 'Confirmed', 'RE': 'Rejected'}[row.state], row.timestamp)
            for row in expected.exclude(state='NW').select_related('marketeer')
        )
        actual_events = sorted(self.ContributorEvent.objects.filter(contributor_id=contributor.pk).values_list('event_id', 'status', 'timestamp'))
        self.assertEqual(actual_events, expected_events)

    def check_sponsor(self, contributor, records):
        matching = sorted((record for record in records if record.company_name == contributor.contributor_name), key=lambda record: record.creation_date)
        latest = matching[-1]
        self.assertEqual((contributor.contributor_type, contributor.email, contributor.description, contributor.contact_name),
                         ('Sponsor', latest.email, latest.description, ''))
        self.assertEqual(self.ContributorHistory.objects.get(contributor_id=contributor.pk, event_type='Create').timestamp,
                         matching[0].creation_date)
        self.assertEqual(
            sorted(self.ContributorEvent.objects.filter(contributor_id=contributor.pk).values_list('event_id', 'status', 'timestamp')),
            sorted((record.event_id, 'Confirmed', record.creation_date) for record in matching if record.confirmed),
        )
        self.assertEqual(
            sorted(self.Contributions.objects.filter(contributor_id=contributor.pk).values_list('event_id', 'gift')),
            sorted((record.event_id, record.gift) for record in matching if record.confirmed and record.gift is not None),
        )
        with_logo = [record for record in matching if record.logo]
        if with_logo:
            original = with_logo[-1]
            self.assertEqual(Path(contributor.icon.path).parent, Path(settings.MEDIA_ROOT) / 'contributors')
            self.assertEqual(Path(contributor.icon.path).name, f'{slugify(contributor.contributor_name)}_logo.jpg')
            with contributor.icon.open('rb') as copied, original.logo.open('rb') as source:
                self.assertEqual(copied.read(), source.read())
        else:
            self.assertFalse(contributor.icon)


class CraftMarketSingleMigration(BaseMigrationTests):
    def seed_records(self):
        event = self.create_event(2025)
        self.event_id = event.pk
        self.marketer = self.create_marketer(event)

    def test_simple_case_migration(self):
        self.assertEqual(self.Contributor.objects.count(), 1)
        contributor = self.Contributor.objects.get()
        self.assertEqual(contributor.contributor_name, 'B&M wood working')
        self.check_marketer(contributor, [self.marketer])

    def test_timestamps_migrated(self):
        self.check_marketer(self.Contributor.objects.get(), [self.marketer])
        self.assertEqual(self.ContributorEvent.objects.filter(event_id=self.event_id).count(), 2)


class CraftMarketMultipleEventMigration(BaseMigrationTests):
    def seed_records(self):
        self.marketers = [
            self.create_marketer(self.create_event(2024), states=('IN', 'RE')),
            self.create_marketer(self.create_event(2025), contact='Linda Wood'),
        ]

    def test_single_contributor(self):
        self.assertEqual(self.Contributor.objects.count(), 1)
        self.check_marketer(self.Contributor.objects.get(), self.marketers)

    def test_history_combined(self):
        self.assertEqual(self.ContributorHistory.objects.count(), 1)
        self.assertEqual(self.ContributorEvent.objects.count(), 4)
        self.check_marketer(self.Contributor.objects.get(), self.marketers)


class CraftMarketMultiContributorMigration(BaseMigrationTests):
    def seed_records(self):
        older, newer = self.create_event(2024), self.create_event(2025)
        # Deliberately create the newer record first: timestamp determines recency.
        self.marketers = [self.create_marketer(newer, states=('IN', 'RE')),
                          self.create_marketer(older, contact='Linda Wood'),
                          self.create_marketer(newer, name='Art by John', contact='John Smith')]

    def test_multiple_contributors(self):
        self.assertEqual(self.Contributor.objects.count(), 2)
        for contributor in self.Contributor.objects.all():
            with self.subTest(name=contributor.contributor_name):
                self.check_marketer(contributor, self.marketers)


class SponsorSingleMigration(BaseMigrationTests):
    def seed_records(self):
        self.sponsors = [self.create_sponsor(self.create_event(2025), confirmed=True, gift='A hamper')]

    def test_simple_case_migration(self):
        self.assertEqual(self.Contributor.objects.count(), 1)
        self.check_sponsor(self.Contributor.objects.get(), self.sponsors)


class SponsorMultipleEventMigration(BaseMigrationTests):
    def seed_records(self):
        self.sponsors = [self.create_sponsor(self.create_event(2024), confirmed=True, gift='A voucher', logo=b'old logo'),
                         self.create_sponsor(self.create_event(2025), confirmed=True, gift='A hamper', logo=b'new logo')]

    def test_simple_case_migration(self):
        self.assertEqual(self.Contributor.objects.count(), 1)
        self.check_sponsor(self.Contributor.objects.get(), self.sponsors)


class SponsorMultipleContributorMigration(BaseMigrationTests):
    def seed_records(self):
        older, newer = self.create_event(2024), self.create_event(2025)
        self.sponsors = [self.create_sponsor(older), self.create_sponsor(newer, confirmed=True, gift='A hamper'),
                         self.create_sponsor(newer, name='Sponsor2', confirmed=True, gift='A voucher')]

    def test_simple_case_migration(self):
        self.assertEqual(self.Contributor.objects.count(), 2)
        for contributor in self.Contributor.objects.all():
            with self.subTest(name=contributor.contributor_name):
                self.check_sponsor(contributor, self.sponsors)


class CombinedSponsorMarketerMigration(BaseMigrationTests):
    def seed_records(self):
        older, newer = self.create_event(2024), self.create_event(2025)
        self.marketers = [self.create_marketer(older, states=('IN', 'RE')),
                          self.create_marketer(newer, contact='Linda Wood'),
                          self.create_marketer(newer, name='Art by John', contact='John Smith')]
        self.sponsors = [self.create_sponsor(older), self.create_sponsor(newer, confirmed=True, gift='A hamper'),
                         self.create_sponsor(older, name='Sponsor2')]

    def test_multi_contributor_migrations(self):
        self.assertEqual(self.Contributor.objects.count(), 4)
        for contributor in self.Contributor.objects.all():
            with self.subTest(name=contributor.contributor_name):
                if contributor.contributor_type == 'Marketer':
                    self.check_marketer(contributor, self.marketers)
                else:
                    self.check_sponsor(contributor, self.sponsors)


class UnconfirmedSponsorMigration(BaseMigrationTests):
    def seed_records(self):
        self.sponsors = [self.create_sponsor(self.create_event(2025), gift='Not confirmed', logo=None)]

    def test_unconfirmed_sponsor_has_no_confirmations_or_contributions(self):
        self.check_sponsor(self.Contributor.objects.get(), self.sponsors)
        self.assertFalse(self.ContributorEvent.objects.exists())
        self.assertFalse(self.Contributions.objects.exists())


class EarlierSponsorLogoMigration(BaseMigrationTests):
    def seed_records(self):
        self.sponsors = [self.create_sponsor(self.create_event(2024), logo=b'earlier logo'),
                         self.create_sponsor(self.create_event(2025), logo=None)]

    def test_earlier_logo_is_preserved_when_latest_record_has_none(self):
        self.check_sponsor(self.Contributor.objects.get(), self.sponsors)
