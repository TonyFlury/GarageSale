import datetime
from pathlib import Path

from django.conf import settings
from django.core.files.uploadedfile import UploadedFile
from django.utils.text import slugify

import CraftMarket
from CraftMarket.models import History, Marketer, MarketerState
from Sponsors.models import Sponsor
from GarageSale.models import EventData
from .__common import TestMigrations

import tempfile
from Contributors.models import Contributor, ContributorHistory, ContributorEvent

import logging
logging.basicConfig(level=logging.DEBUG)

# Turn off the default logging for CraftMarket models
logger = logging.getLogger("CraftMarket.models")
logger.setLevel(logging.WARNING)


class BaseMigrationTests(TestMigrations):
    """Base class for migration tests"""
    migrate_from = []
    migrate_to = []
    def __init__(self, *args, **kwargs):
        cls = self.__class__
        cls.migrate_from = [('CraftMarket', cls.last_migration('CraftMarket')),
                                             ('Contributors', None)]
        cls.migrate_to = [('CraftMarket', cls.last_migration('CraftMarket')),
                                            ('Contributors', cls.first_migration('Contributors')) ]

        super().__init__(*args, **kwargs)

    def check_history(self, contributor):
        return

class MarketerMigrationsBase(BaseMigrationTests):
    def __init__(self, *args, **kwargs):
        self.cms=[]
        self.events=[]
        super().__init__(*args, **kwargs)

    def fix_history(self):
        """Correct the history for all marketeers in self.cms"""
        for marketer in self.cms:
            event_date = datetime.datetime.combine(marketer.event.event_date,
                                                   datetime.time.min, tzinfo=datetime.UTC)
            marketer.history.filter(state='NW').update(timestamp=event_date - datetime.timedelta(days=30))
            marketer.history.filter(state='IN').update(timestamp=event_date - datetime.timedelta(days=29))
            marketer.history.filter(state='CO').update(timestamp=event_date - datetime.timedelta(days=25))
            marketer.history.filter(state='Re').update(timestamp=event_date - datetime.timedelta(days=25))

    def check_history(self, contributor):
        """Check the migrated history is the same as the original"""
        if contributor.contributor_type == 'Marketer':
            for event in self.events:
                with self.subTest(event=event, msg=f'Checking history for all contributors for event {event}'):
                    # The old history per event
                    event_history = History.objects.filter(marketeer__trading_name=contributor.contributor_name,
                                                           marketeer__event=event).exclude(state='NW').order_by('timestamp')
                    # The contributor event history
                    contributor_event_history = ContributorEvent.objects.filter(contributor=contributor, event=event).order_by(
                        'timestamp')

                    # Counts should be the same as a minimum
                    self.assertEqual(event_history.count(), contributor_event_history.count(),
                                     f' Counts for {event} do not agree {event_history.count()=} {contributor_event_history.count()=}')

                    # For each history and contributor event, check that the status and timestamp agree
                    for cm_history_item, co_history_item in zip(event_history, contributor_event_history):
                        self.assertEqual({'IN': 'Invited', 'CO': 'Confirmed', 'RE': 'Rejected'}[cm_history_item.state],
                                         co_history_item.status)
                        self.assertEqual(cm_history_item.timestamp, co_history_item.timestamp)
        super().check_history(contributor)


class CraftMarketSingleMigration(MarketerMigrationsBase,):
    """Test single migrated CraftMarket Instance is migrated correctly - ie
    a single contributor is created with the correct details
    and a single history record and HistoryEvent is created"""
    def setUpBeforeMigration(self, apps):
        """Create a basic instance for a marketer"""
        self.event = EventData.objects.create( event_date = datetime.date(year=2025, month=6, day=20), use_from = datetime.date(year=2025, month=6, day=19))

        instance = Marketer.objects.create( event = self.event,
                           trading_name= 'B&M wood working', email='bm.wood_working@marketer.com',
                          contact_name='Bary wood')

        self.new_time_stamp = History.objects.filter(marketeer=instance, state='NW').first().timestamp

        instance.update_state(MarketerState.Invited, send_email=False)

        self.invite_time_stamp = History.objects.filter(marketeer=instance, state=MarketerState.Invited).first().timestamp

        instance.update_state(MarketerState.Confirmed, send_email=False)
        self.confirm_time_stamp = History.objects.filter(marketeer=instance, state=MarketerState.Confirmed).first().timestamp

    def test_simple_case_migration(self):
        contributor_list = Contributor.objects.all()
        self.assertEqual(len(contributor_list), 1)
        contributor = contributor_list[0]
        self.assertEqual(contributor.contributor_type, 'Marketer')
        self.assertEqual(contributor.contributor_name, 'B&M wood working')
        self.assertEqual(contributor.email, 'bm.wood_working@marketer.com')

    def test_timestamps_migrated(self):
        contributor_list = Contributor.objects.all()
        self.assertEqual(len(contributor_list), 1)
        contributor = contributor_list[0]

        creation = ContributorHistory.objects.filter(contributor=contributor,
                                                     event_type='Create')
        self.assertEqual(creation.count(), 1)
        self.assertEqual(creation[0].timestamp, self.new_time_stamp)

        invite = ContributorEvent.objects.filter(contributor=contributor,status='Invited', event=self.event)
        self.assertEqual(invite.count(), 1)
        self.assertEqual(invite[0].timestamp, self.invite_time_stamp)

        confirm = ContributorEvent.objects.filter(contributor=contributor,status='Confirmed', event=self.event)
        self.assertEqual(confirm.count(), 1)
        self.assertEqual(confirm[0].timestamp, self.confirm_time_stamp)

    #ToDO - test two CraftMarketer instances with the same name on different events.

class CraftMarketMultipleEventMigration(MarketerMigrationsBase):
    """Test two CraftMarket Instances for the same trader on different events are migrated correctly - ie
    a single contributor is created with the correct details
    and a single history record and the appropriate HistoryEvents are created"""
    def setUpBeforeMigration(self, apps):
        """Create a basic instance for a marketer on multiple events.
           This should record only one contributor with details from the most recent
           the combined history should reflect both instances.
        """
        self.events = [ EventData.objects.create( event_date = datetime.date(year=2025, month=6, day=20), use_from = datetime.date(year=2025, month=6, day=19)),
                        EventData.objects.create( event_date = datetime.date(year=2024, month=6, day=20), use_from = datetime.date(year=2024, month=6, day=19)) ]

        self.cms = [Marketer.objects.create(event = self.events[1], trading_name='B&M wood working',
                                           email='bm.wood_working@marketer.com',
                                           contact_name='Bary wood'),
                    Marketer.objects.create(event=self.events[0], trading_name='B&M wood working',
                                            email='bm.wood_working@marketer.com',
                                            contact_name='Linda Wood') ]

        self.cms[0].update_state(MarketerState.Invited, send_email=False)
        self.cms[0].update_state(MarketerState.Rejected, send_email=False)

        self.cms[1].update_state(MarketerState.Invited, send_email=False)
        self.cms[1].update_state(MarketerState.Confirmed, send_email=False)

        # Fix history for the marketer to be more realistic.
        # For the sake of the migration, make the record so that the marketer is created 30 days before the event
        # Invites are sent 25 days before the event, and Confirmation/Rejections are marked 25 days before.
        self.fix_history()

    def test_single_contributor(self):
        """Confirm that only one contributor is created with details from the most recent event"""
        contributors = Contributor.objects.all()
        self.assertEqual(len(contributors),1)
        co = contributors[0]
        latest = max(self.cms, key=lambda x: x.event.event_date)
        earliest = min(self.cms, key=lambda x: x.event.event_date)

        self.assertEqual(co.contributor_type, 'Marketer')
        self.assertEqual(co.contributor_name, latest.trading_name)
        self.assertEqual(co.email, latest.email)
        self.assertEqual(co.contact_name, latest.contact_name)

    def test_history_combined(self):
        """Confirm that the combined history records the two events"""
        co = Contributor.objects.all()[0]
        history = ContributorHistory.objects.filter(contributor=co)
        latest = max(self.cms, key=lambda x: x.event.event_date)
        earliest = min(self.cms, key=lambda x: x.event.event_date)

        # Only one history event - the creation of this contributor
        self.assertEqual(history.count(), 1)
        self.assertEqual(history[0].event_type, 'Create')
        self.assertEqual(history[0].timestamp,
                        earliest.history.filter(state=MarketerState.New).first().timestamp)

        # Check event history - there should be 4 events - 2 invites, 1 Reject and 1 confirm
        event_history = ContributorEvent.objects.filter(contributor=co)
        self.assertEqual(event_history.count(), 4)

        # For every fundraising event, there check that the history records the same status and timestamp
        self.check_history( co )

class CraftMarketMultiContributorMigration(MarketerMigrationsBase):
    """Test two different CraftMarket Instances for different traders
     on different events are migrated correctly - ie
     Multiple contributors are created with the correct details
     The correct history records are created, and the appropriate HistoryEvents are created"""
    def setUpBeforeMigration(self, apps):
        """Create a set of instances for multiple marketers on multiple events.
           This should record only one contributor with details from the most recent
           the combined history should reflect both instances.
        """
        self.events = [ EventData.objects.create( event_date = datetime.date(year=2025, month=6, day=20),
                                                  use_from = datetime.date(year=2025, month=6, day=19)),
                        EventData.objects.create( event_date = datetime.date(year=2024, month=6, day=20),
                                                  use_from = datetime.date(year=2024, month=6, day=19)) ]

        self.cms = [Marketer.objects.create(event = self.events[0], trading_name='B&M wood working',
                                           email='bm.wood_working@marketer.com',
                                           contact_name='Bary wood'),
                    Marketer.objects.create(event=self.events[1], trading_name='B&M wood working',
                                            email='bm.wood_working@marketer.com',
                                            contact_name='Linda Wood'),
                    Marketer.objects.create(event=self.events[0], trading_name='Art by John',
                                            email='art@marketer.com',
                                            contact_name='John Smith')]

        # Invite the first Marketer to the relevant, with a rejection event.
        self.cms[0].update_state(MarketerState.Invited, send_email=False)
        self.cms[0].update_state(MarketerState.Rejected, send_email=False)

        # Invite and confirm the second Marketer to the relevant, with a confirmation event.
        self.cms[1].update_state(MarketerState.Invited, send_email=False)
        self.cms[1].update_state(MarketerState.Confirmed, send_email=False)

        # Invite and confirm the third Marketer to the relevant, with a confirmation event.
        self.cms[2].update_state(MarketerState.Invited, send_email=False)
        self.cms[2].update_state(MarketerState.Confirmed, send_email=False)

        # Fix history for the marketer to be more realistic.
        self.fix_history()

    def test_multiple_contributors(self):
        """Confirm that only one contributor is created with details from the most recent event"""
        contributors = Contributor.objects.all()
        self.assertEqual(len(contributors), 2)

        # Of the two contributors - the data for the first should be that for 2nd Marketer - as it
        # more recent than the first entry for the same trader.
        # Should test this in case the migrations are out of order
        for contributor in contributors:
            with self.subTest(contributor=contributor, msg=f'Checking history for all contributors for {contributor}'):
                # find the latest original marketer from the test data
                all = [item for item in self.cms if item.trading_name==contributor.contributor_name]
                latest = max(all, key=lambda x: x.event.event_date)
                earliest = min(all, key=lambda x: x.event.event_date)

                self.assertEqual(contributor.contributor_type, 'Marketer')
                self.assertEqual(contributor.contributor_name, latest.trading_name)
                self.assertEqual(contributor.email, latest.email)
                self.assertEqual(contributor.contact_name, latest.contact_name)

                # Check the creation date is correctly recorded
                creation = ContributorHistory.objects.filter(contributor=contributor, event_type='Create')
                self.assertEqual(creation.count(), 1)
                self.assertEqual(creation[0].timestamp, earliest.history.filter(state=MarketerState.New).first().timestamp)

                self.check_history(contributor)

class SponsorMigrationsBase(BaseMigrationTests):
    """Base class for migration tests"""

    def __init__(self, *args, **kwargs):
        self.logo=[]
        self.sponsors=[]
        self.events=[]
        self.upload_files=[]
        super().__init__(*args, **kwargs)

    def check_history(self, contributor):
        """Check the migrated history is the same as the original"""

        if contributor.contributor_type == 'Sponsor':
            earliest = min([sponsor for sponsor in self.sponsors if sponsor.company_name == contributor.contributor_name],
                           key=lambda x: x.creation_date)
            co_history = ContributorHistory.objects.filter(contributor=contributor, event_category='Data',
                                                               event_type='Create', timestamp=earliest.creation_date)
            self.assertEqual(co_history.count(), 1)
            for sponsor_history, con_history in zip(
                    Sponsor.objects.filter(company_name=contributor.contributor_name).order_by('creation_date'),
                    ContributorEvent.objects.filter(contributor=contributor, status='Confirm').order_by('timestamp')):
                self.assertEqual(sponsor_history.creation_date, con_history.timestamp)
                self.assertEqual(sponsor_history.event, con_history.event)

        super().check_history(contributor)

    def check_icon(self,contributor):
        """Check the icon is created and has the correct name and location"""
        latest = [sponsor for sponsor in self.sponsors if sponsor.company_name == contributor.contributor_name][-1]
        self.assertEqual(Path(contributor.icon.path).name,
                         f'{Path(latest.logo.path).name}')
        self.assertEqual(Path(contributor.icon.path).parent, Path(settings.MEDIA_ROOT).absolute()/'contributors')

        with open(contributor.icon.path, 'rb') as f:
            self.assertEqual(f.read(), latest.logo.read())

class SponsorSingleMigration(SponsorMigrationsBase):
    """Test a single Spoonsor Instance is migrated correctly - ie
    a single contributor is created with the correct details
    and a single history record and HistoryEvent is created"""
    def setUpBeforeMigration(self, apps):
        """Create a basic instance for a sponsor"""
        self.logo = [tempfile.NamedTemporaryFile(suffix=".jpg")]
        for index, l in enumerate(self.logo):
            with open(l.name, 'wb') as f:
                f.write(f'logo {index}'.encode(encoding='utf-8'))
        self.upload_files = [UploadedFile(open(self.logo[0].name, 'rb'), self.logo[0].name, content_type='image/jpeg')]
        self.event = [EventData.objects.create( event_date = datetime.date(year=2025, month=6, day=20), use_from = datetime.date(year=2025, month=6, day=19))]
        self.sponsors = [Sponsor.objects.create( event=self.event[0], company_name='Sponsor1', logo=self.upload_files[0],
                                                description='Sponsor for event 0',
                                               email='sponsor1@sponsors.com')]

    def test_simple_case_migration(self):
        contributors = Contributor.objects.all()
        self.assertEqual(contributors.count(), 1)
        co = contributors[0]
        sp = self.sponsors[0]
        self.assertEqual((co.contributor_type, co.contributor_name, co.email, co.description, co.contact_name),
                         ('Sponsor', sp.company_name, sp.email, sp.description, '') )

        #Check history
        self.check_history(co)
        self.check_icon(co)

class SponsorMultipleEventMigration(SponsorMigrationsBase):
    """Test a Multiple Spoonsor Instance on the different event are migrated correctly - ie
    a single contributor is created with the correct details
    and a single history record and HistoryEvent is created"""
    def setUpBeforeMigration(self, apps):
        """Create a basic instance for a sponsor"""

        self.logo = [tempfile.NamedTemporaryFile(suffix=".jpg"), tempfile.NamedTemporaryFile(suffix=".jpg")]
        for index, l in enumerate(self.logo):
            with open(l.name, 'wb') as f:
                f.write(f'logo {index}'.encode(encoding='utf-8'))
        self.upload_files = [UploadedFile(open(logo.name, 'rb'), logo.name, content_type='image/jpeg') for logo in self.logo]
        self.event = [EventData.objects.create( event_date = datetime.date(year=2024, month=6, day=20),
                                                use_from = datetime.date(year=2024, month=6, day=19)),
                      EventData.objects.create(event_date=datetime.date(year=2025, month=6, day=20),
                                               use_from=datetime.date(year=2025, month=6, day=19)),
                      ]

        self.sponsors = [Sponsor.objects.create( event=self.event[0], company_name='Sponsor1', logo=self.upload_files[0],
                                               description='Sponsor for event 1',
                                               email='sponsor1@sponsors.com'),
                         Sponsor.objects.create(event=self.event[1], company_name='Sponsor1', logo=self.upload_files[1],
                                                description='Sponsor for event 2',
                                                email='sponsor1@sponsors.com')
                         ]

    def test_simple_case_migration(self):
        contributors = Contributor.objects.all()
        self.assertEqual(contributors.count(), 1)
        co = contributors[0]

        # latest entry for this sponsor is the last entry
        sp = [sponsor for sponsor in self.sponsors if sponsor.company_name == co.contributor_name][-1]
        self.assertEqual((co.contributor_type, co.contributor_name, co.email, co.description, co.contact_name),
                         ('Sponsor', sp.company_name, sp.email, sp.description, '') )

        #Check history
        self.check_history(co)
        self.check_icon(co)

class SponsorMultipleContributorMigration(SponsorMigrationsBase):
    """Test a Multiple Spoonsor Instance on the different event are migrated correctly - ie
    a single contributor is created with the correct details
    and a single history record and HistoryEvent is created"""
    def setUpBeforeMigration(self, apps):
        """Create a basic instance for a sponsor"""

        self.logo = [tempfile.NamedTemporaryFile(suffix=".jpg"), tempfile.NamedTemporaryFile(suffix=".jpg"), tempfile.NamedTemporaryFile(suffix=".jpg")]
        for index, l in enumerate(self.logo):
            with open(l.name, 'wb') as f:
                f.write(f'logo {index}'.encode(encoding='utf-8'))
        self.upload_files = [UploadedFile(open(logo.name, 'rb'), logo.name, content_type='image/jpeg') for logo in self.logo]
        self.event = [EventData.objects.create( event_date = datetime.date(year=2024, month=6, day=20),
                                                use_from = datetime.date(year=2024, month=6, day=19)),
                      EventData.objects.create(event_date=datetime.date(year=2025, month=6, day=20),
                                               use_from=datetime.date(year=2025, month=6, day=19)),
                      ]

        self.sponsors = [Sponsor.objects.create( event=self.event[0], company_name='Sponsor1', logo=self.upload_files[0],
                                               description='Sponsor for event 1',
                                               email='sponsor1@sponsors.com'),
                         Sponsor.objects.create(event=self.event[1], company_name='Sponsor1', logo=self.upload_files[1],
                                                description='Sponsor for event 2',
                                                email='sponsor1@sponsors.com'),
                         Sponsor.objects.create(event=self.event[1], company_name='Sponsor2', logo=self.upload_files[2],
                                                description='Sponsor for event 2',
                                                email='sponsor2@sponsors.com')
                         ]

    def test_simple_case_migration(self):
        contributors = Contributor.objects.all()
        self.assertEqual(contributors.count(), len(set([sponsor.company_name for sponsor in self.sponsors])))
        for co in contributors:
            # latest entry for this sponsor is the last entry
            sp = [sponsor for sponsor in self.sponsors if sponsor.company_name == co.contributor_name][-1]
            self.assertEqual((co.contributor_type, co.contributor_name, co.email, co.description, co.contact_name),
                             ('Sponsor', sp.company_name, sp.email, sp.description, '') )

            #Check history
            self.check_history(co)
            self.check_icon(co)

class CombinedSponsorMarketerMigration(SponsorMigrationsBase, MarketerMigrationsBase):
    """Test a Multiple Spoonsor Instance on the different event are migrated correctly - ie
    a single contributor is created with the correct details
    and a single history record and HistoryEvent is created"""
    def setUpBeforeMigration(self, apps):

        self.logo = [tempfile.NamedTemporaryFile(suffix=".jpg"), tempfile.NamedTemporaryFile(suffix=".jpg"), tempfile.NamedTemporaryFile(suffix=".jpg")]
        self.upload_files = [UploadedFile(open(logo.name, 'rb'), logo.name, content_type='image/jpeg') for logo in self.logo]
        self.events = [EventData.objects.create( event_date = datetime.date(year=2024, month=6, day=20),
                                                  use_from = datetime.date(year=2024, month=6, day=19)),
                        EventData.objects.create(event_date=datetime.date(year=2025, month=6, day=20),
                                                 use_from=datetime.date(year=2025, month=6, day=19)),
                        ]
        self.cms = [Marketer.objects.create(event=self.events[0], trading_name='B&M wood working',
                                            email='bm.wood_working@marketer.com',
                                            contact_name='Bary wood'),
                    Marketer.objects.create(event=self.events[1], trading_name='B&M wood working',
                                            email='bm.wood_working@marketer.com',
                                            contact_name='Linda Wood'),
                    Marketer.objects.create(event=self.events[0], trading_name='Art by John',
                                            email='art@marketer.com',
                                            contact_name='John Smith')]

        # Invite the first Marketer to the relevant, with a rejection event.
        self.cms[0].update_state(MarketerState.Invited, send_email=False)
        self.cms[0].update_state(MarketerState.Rejected, send_email=False)

        # Invite and confirm the second Marketer to the relevant, with a confirmation event.
        self.cms[1].update_state(MarketerState.Invited, send_email=False)
        self.cms[1].update_state(MarketerState.Confirmed, send_email=False)

        # Invite and confirm the third Marketer to the relevant, with a confirmation event.
        self.cms[2].update_state(MarketerState.Invited, send_email=False)
        self.cms[2].update_state(MarketerState.Confirmed, send_email=False)

        self.fix_history()
        self.sponsors = [Sponsor.objects.create( event=self.events[0], company_name='Sponsor1', logo=self.upload_files[0],
                                                 description='Sponsor for event 0',),
                         Sponsor.objects.create(event=self.events[1], company_name='Sponsor1', logo=self.upload_files[1],
                                                description='Sponsor for event 1',),
                         Sponsor.objects.create(event=self.events[0], company_name='Sponsor2', logo=self.upload_files[2],
                                                description='Sponsor for event 2',)]

    def test_multi_contributor_migrations(self):

        # Based on the data we will have 4 contributors
        contributors = Contributor.objects.all()
        self.assertEqual(contributors.count(), len(set(sponsor.company_name for sponsor in self.sponsors)) +
                                                 len(set(cms.trading_name for cms in self.cms)))
        for co in contributors:
            match co.contributor_type:
                case 'Marketer':
                    with self.subTest(f'Checking marketer {co.contributor_name}'):
                        entry = [cms for cms in self.cms if cms.trading_name == co.contributor_name][-1]
                        self.assertEqual((co.contributor_type, co.contributor_name, co.email, co.contact_name, co.description, ),
                                 ('Marketer', entry.trading_name, entry.email, entry.contact_name, ''))
                        self.check_history(co)
                case 'Sponsor':
                    with self.subTest(f'Checking Sponsor {co.contributor_name}'):
                        # latest entry for this sponsor is the last entry
                        sp = [sponsor for sponsor in self.sponsors if sponsor.company_name == co.contributor_name][-1]
                        self.assertEqual((co.contributor_type, co.contributor_name, co.email, co.description, co.contact_name),
                                 ('Sponsor', sp.company_name, sp.email, sp.description, '') )
                        self.check_history(co)
                        self.check_icon(co)
