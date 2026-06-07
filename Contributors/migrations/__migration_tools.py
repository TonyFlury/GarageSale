from pathlib import Path
from typing import Any, TypeVar
import json

from django.core.files.base import ContentFile
from django.db import models

from django.db.models import Model
from django.utils.text import slugify

from Contributors.models import Contributor

"""
A set of helper functions to migrate from Sponsors and Marketers to the new Contributor model

These functions reconstruct the event history for the new contributor instance, make it easier to find the earliest and
latest original data instances, and make mapping from between fields.

The migration is done in two steps:
1. Create the new contributor instance
2. Create the new contributor history instances

The process is complex enough that these helper classes are needed to simply the actual migration script.

"""
#TODO : should we have two 'helper' classes - one for Marketers and one for Sponsors  - and use composition ?

_T = TypeVar('_T')

class DataEnumerator:
    unique_identifier_field = {'CraftMarket': 'trading_name', 'Sponsors': 'company_name'}

    data_models: dict[str, dict[str, str]] = \
        {'CraftMarket': {'data': 'Marketer', 'history': 'History', 'data_type': 'Marketer'},
        'Sponsors': {'data': 'Sponsor', 'data_type': 'Sponsor'}}

    def __init__(self, apps):
        self.app = ''
        self.apps = apps

    def enumerate(self):
        for app, data in self.data_models.items():
            data_model: models.Model = self.apps.get_model(app, data['data'])
            cm_names = set(data_model.objects.values_list(self.unique_identifier_field[app], flat=True))
            for contributor_name in cm_names:
                yield app, MigrationHelper(app, self.apps, contributor_name, data['data_type'])

class MigrationHelper :
    def __init__(self, app: str, apps, contributor_name: str, data_type: str):
        self.app = app
        self.apps = apps
        self.data_type = data_type
        self.contributor_name = contributor_name
        self.field_map:dict[str,str] = {'CraftMarket': {'contributor_name': 'trading_name', 'logo': 'icon'},
                'Sponsors': {'contributor_name': 'trading_name', 'logo': 'logo'} }[self.app]
        self.unique_identifier_field = DataEnumerator.unique_identifier_field[self.app]
        self.socials = {'website', 'facebook', 'instagram'}
        self.contributor_model, self.contributor_event_model, self.contributor_history_model, self.contributions_model= (
            apps.get_model('Contributors', 'Contributor'),
            apps.get_model('Contributors', 'ContributorEvent'),
            apps.get_model('Contributors', 'ContributorHistory'),
            apps.get_model('Contributors', 'Contributions'),
        )
        self.data_models = DataEnumerator.data_models[self.app]

        self.data_model:Model = apps.get_model(self.app, self.data_models['data'])

        self.earliest_date, self.most_recent_obj = self.get_most_recent()

    def mapped_fields(self ):
        socials_dict = {social: getattr(self.most_recent_obj, social) for social in self.socials}

        return {'contributor_type' : self.data_type,
                'contributor_name' : self.contributor_name,
                'email': self.get_mapped_field(self.most_recent_obj, 'email', ''),
                'contact_name': self.get_mapped_field(self.most_recent_obj, 'contact_name', ''),
                'description': self.get_mapped_field(self.most_recent_obj, 'description', ''),
                'socials' : json.dumps(socials_dict)
                }

    def migrate_history(self, contributor: Contributor):
            match self.app:
                case 'CraftMarket':
                    self._construct_marketer_history( contributor)
                case 'Sponsors':
                    self._construct_sponsor_history( contributor)
                case _:
                    raise ValueError(f'Unknown app {self.app}')

    def _construct_marketer_history(self, contributor: Contributor):
        """Construct the Event history based on the history data for this Marketer """
        self.history_model = self.apps.get_model(self.app, 'History')

        contributor_name = contributor.contributor_name
        for each_history in self.history_model.objects.filter(marketeer__trading_name=contributor_name).all():
            match each_history.state:
                case 'NW':
                    continue
                case 'IN' | 'CO' | 'RE':
                    self.contributor_event_model.objects.create(contributor=contributor,
                                                           event=each_history.marketeer.event,
                                                           status={'IN': 'Invited',
                                                                   'CO': 'Confirmed',
                                                                   'RE': 'Rejected'}[each_history.state],
                                                           timestamp=each_history.timestamp)


    def _construct_sponsor_history(self, contributor: Contributor):
        """There is no history in this case, so we recreate a pseudo history based on the low level data
           for example : confirmation date is not recorded at all, so we pretend that the contribution is confirmed on the
           creation date.
           We have no tracking of any data changes
        """
        sponsor_data = self.data_model.objects.filter( **{self.unique_identifier_field: contributor.contributor_name} ).order_by('creation_date')

        # Record a 'confirmation date' for each event this sponsor exists
        for entry in sponsor_data:
            if getattr(entry, 'confirmed') is True:
                self.contributor_event_model.objects.create( contributor=contributor, event = entry.event,
                                                        timestamp=entry.creation_date, status='Confirmed',
                                                        )
                if getattr(entry, 'gifts') is not None:
                    self.contributions_model.objects.create(
                        contributor=contributor,
                        event=entry.event,
                        gift=getattr(entry, 'gifts'),
                    )

    def get_mapped_field(self, obj: object, field_name:str, default:_T=None):
        """Map from a contributor field name to the app specific field name"""
        actual_field:str = self.field_map.get(field_name, field_name)
        return getattr(obj, actual_field, default)

    def get_most_recent(self) -> tuple[Any, Any]:
        # Identify first and most recent entries for this contributor
        if self.app == 'CraftMarket':
            history_model = self.apps.get_model('CraftMarket', 'History')
            this_contributor_history = history_model.objects.filter(marketeer__trading_name=self.contributor_name, state='NW').order_by(
                'timestamp')
            creation_date = this_contributor_history.first().timestamp
            most_recent_info = this_contributor_history.last().marketeer
        else:
            history_model = None
            this_contributor = self.data_model.objects.filter(company_name=self.contributor_name).order_by('creation_date')
            creation_date = this_contributor.first().creation_date
            most_recent_info = this_contributor.last()
        return creation_date, most_recent_info


    def migrate_logo(self, contributor: Contributor):
        logo_field = self.field_map.get('logo', 'logo')
        if self.app == 'CraftMarket':
            order_by = 'event__event_date'
        else:
            order_by = 'creation_date'

        most_recent_with_logo = (self.data_model.objects.filter(**{self.unique_identifier_field: self.contributor_name}).
                                 exclude(**{f'{logo_field}__isnull': True}).
                                 exclude(**{logo_field: ""}).
                                 order_by(order_by).last())

        existing_logo_image: models.ImageField|None = self.get_mapped_field(most_recent_with_logo, 'logo')
        if existing_logo_image and existing_logo_image.name:
            # The existing logo will have the company name slug as a prefix - so remove it
            file_name = Path(existing_logo_image.path).name
            slug = slugify(self.contributor_name)
            if file_name.startswith(slug+'_'):
                file_name = file_name[len(slug)+1:]
            with existing_logo_image.storage.open( existing_logo_image.name, 'rb') as source:
                contributor.icon.save(file_name,
                                          ContentFile(source.read()), save=True)
        contributor.save()