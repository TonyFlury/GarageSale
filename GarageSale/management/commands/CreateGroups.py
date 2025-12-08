from collections import defaultdict
from functools import partial
from typing import Any

from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.apps import apps

import logging

import CraftMarket
from GarageSale.management.commands._WildcardDict import WildcardDict

logger = logging.getLogger('GarageSale.management.createGroups')
logger.addHandler(logging.StreamHandler())
logger.setLevel(logging.DEBUG)

default_permissions = ['add', 'edit', 'view', 'delete']

# Hard code non-default permissions for specific models
model_permissions = defaultdict(partial(defaultdict, list), {
                                    'GarageSale': {'supporting':['create','+'], },
                                    'CraftMarket': {'marketer':['can_suggest','edit','view','delete'],},
                                    'Accounts': {'transaction':['upload','edit','view', 'report']}
                     })

groups = {'ExecMember':{'*:not(CraftMarket,Accounts,Sponsors)|*|view',
                        'CraftMarket|marketer|can_suggest',
                        'Sponsor|sponsor|can_suggest'},
          'WebAdmin':{'*|*|*'},
          'Officer':{'*:not(CraftMarket,Sponsor,Accounts)|*|*:not(delete)'},
          'Financier':{'Accounts|*|*'},
          'CraftMarketManager':{'CraftMarket|*|*'},
          'SponsorshipManager':{'Sponsors|*|*'},
          }

found_perms = WildcardDict()


class Command( BaseCommand ):
    help_text = 'Create permission groups for the website users'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._verbose = False

    def add_arguments(self, parser):

        # Allow user to specify a group and app.model to create permissions for
        parser.add_argument("group", nargs='?', type=str, default=None, help="The group to create permissions for")
        parser.add_argument("app_model", nargs='?', type=str, default=None, help="The app.model to create permissions for")

        # Allow user to implement a fake set of actions.
        parser.add_argument(
            "--fake",
            action="store_true",
            help="Show what would happen, but don't actually do it.",
        )

        # Allow user to implement a fake set of actions.
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Repprt actions as they are performed.",
        )

        # Allow user to prevent deletion of permissions
        parser.add_argument(
            "--no_delete",
            action="store_true",
            help="Prevent deletion of existing and permissions.",
        )

        parser.add_argument(
            "--no_delete_group",
            action="store_false",
            help="Prevent deletion of existing group permissions.",
        )

    def verbose(self, msg:str):
        if self._verbose:
            logging.info(msg)

    def handle(self, *args, **options):
        # Build permissions based on their names

        self._verbose = options['verbose']

        group_option = options['group'] if options['group'] else None
        if not options['app_model']:
            app_option, model_option = None, None
        elif '.' in options['app_model']:
            app_option, model_option = options['app_model'].split('.')
        else:
            app_option, model_option = options['app_model'][0], None

        model_option = None if not model_option else model_option.lower()

        # Enumerate all non-django apps and models
        self._enumerate_models(app_option, model_option, options)

        # Create permissions on the relevant models
        self._create_permissions(app_option, model_option, options)

        # Build groups as expected
        self._build_groups(group_option, options)


    def _build_groups(self, group_option: Any | None, options: dict[str, Any]):
        for group_name, perm_list in groups.items():
            if group_option and group_name != group_option:
                continue

            if not options['no_delete_group']:
                if options['fake']:
                    logging.info(f'Removing all existing groups named {group_name}')
                else:
                    self.verbose(f'Removing all existing groups named {group_name}')
                    Group.objects.filter(name=group_name).delete()

            if options['fake']:
                logging.info(f'Creating group {group_name}')
                group = object()
            else:
                group = Group.objects.get_or_create(name=group_name)[0]

            for perm in perm_list:
                for app, model, name, perms in found_perms.enumerate(perm):
                    if options['fake']:
                        logger.info(f'Adding {app}.{model} | {name} for {group_name}')
                    else:
                        self.verbose(f'Adding {app}.{model} | {name} for {group_name}')
                        group.permissions.add(perms)


    def _create_permissions(self, app_option, model_option, options: dict[str, Any]):
        for app, model_perms in model_permissions.items():
            if app_option and app != app_option:
                continue
            for model, perms in model_perms.items():
                if model_option and model != model_option:
                    continue

                try:
                    ctype = ContentType.objects.get(app_label=app, model=model.lower())
                except ContentType.DoesNotExist:
                    logger.error(f'Unable to find content type for {app}.{model}')
                    continue

                if not options['no_delete']:
                    if options['fake']:
                        logging.info(f'Removing all existing perms from {app}.{model}')
                    else:
                        self.verbose(f'Removing all existing perms from {app}.{model}')
                        Permission.objects.filter(content_type=ctype).delete()

                for perm in perms:
                    if options['fake']:
                        logging.info(f'Adding {perm} to {app}.{model}')
                        found_perms[app][model].add((perm, object()))
                    else:
                        self.verbose(f'Adding {perm} to {app}.{model}')
                        p = Permission.objects.get_or_create(codename=perm, content_type=ctype, name=f'{perm}')[0]
                        found_perms[app][model].add((perm, p))


    def _enumerate_models(self, app_option, model_option, options: dict[str, Any]):
        for models in apps.get_models():
            app_name, model_name = models._meta.app_label, models._meta.model_name
            if models.__module__.startswith('django'):
                continue
            perms = model_permissions.get(app_name, {}).get(model_name, [])

            if app_option and app_name != app_option:
               continue

            if model_option and model_name != model_option:
                continue

            if not perms:
                model_permissions[app_name][model_name] = default_permissions
            elif '+' in perms:
                existing = list(set(perms) - set('+'))
                model_permissions[app_name][model_name] = existing + default_permissions