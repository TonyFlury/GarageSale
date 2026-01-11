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
from itertools import groupby

logger = logging.getLogger('GarageSale.management.createGroups')
logger.addHandler(logging.StreamHandler())
logger.setLevel(logging.DEBUG)

default_permissions = {'add', 'change', 'view', 'delete'}

# Hard code non-default permissions for specific models
# Permissions preceded by a '-' shouldn't exist
# A '-'  on its own means that none of the default permissions shouldn't exist
model_permissions = defaultdict(partial(defaultdict, list), {
                                    'GarageSale' : {'general':['is_team_member', 'is_trustee', 'is_administrator', 'is_manager', '-'],
                                                    'supporting':['create'], },
                                    'Sponsors': {'sponsor':['suggest','confirm', '-add'],},
                                    'CraftMarket': {'marketer':['suggest','-add'],},
                                    'News': {'newsarticle':['publish',]},
                                    'Accounts': {'transaction':['upload','report', '-add']}
                     })

groups = {'ExecMember':{'*:not(CraftMarket,Accounts,Sponsors)|*|view',
                        'CraftMarket|marketer|suggest',
                        'Sponsor|sponsor|suggest'},
          'WebAdmin':{'*|*|*'},
          'Officer':{'*:not(CraftMarket,Sponsor,Accounts)|*|*:not(delete)'},
          'Financier':{'Accounts|*|*'},
          'CraftMarketManager':{'CraftMarket|*|*'},
          'SponsorshipManager':{'Sponsors|*|*'},
          }



class Command( BaseCommand ):
    help_text = 'Create permission groups for the website users'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._verbose = 0

        self.found_perms = WildcardDict()

    def add_arguments(self, parser):

        # Allow user to specify a group and app.model to create permissions for
        parser.add_argument("-g", "--group", nargs=1, type=str, default=None, help="The group to create permissions for")
        parser.add_argument("-m", "--app_model", nargs=1, type=str, default=None, help="The app.model to create permissions for")

        # Allow user to prevent deletion of permissions
        parser.add_argument(
            "--autofix",
            action="store_true",
            help="Automatically fix missing permissions on tables or in groups.",
        )

    def vb(self, level, msg:str):
        if self._verbose >= level:
            print(msg)

    def verbose(self, msg:str):
        if self._verbose:
            print(msg)

    def handle(self, *args, **options):
        # Build permissions based on their names

        self._verbose = options.get('verbosity', 0)
        # Work out group and models from options.
        group_option = options['group'] if options['group'] else None
        if not options['app_model']:
            app_option, model_option = None, None
        elif '.' in options['app_model']:
            app_option, model_option = options['app_model'].split('.')
        else:
            app_option, model_option = options['app_model'][0], None

        model_option = None if not model_option else model_option.lower()

        # Enumerate all non-django apps and models
        self._identify_models_and_permissions(app_option, model_option, options)

        # Check permissions on the relevant models
        self._check_permissions(app_option, model_option, options)

        if group_option:
            # Build groups as expected
            self._check_groups(group_option, app_option, model_option, options)


    def _check_groups(self, group_option: Any | None, app_option : str|None, model_option: str|None, options: dict[str, Any]):
        """Build the groups as expected"""
        for group_name, perm_list in groups.items():
            if group_option and group_name != group_option:
                continue

            try:
                group = Group.objects.get(name=group_name)
            except Group.DoesNotExist:
                print(f'Group {group_name} does not exist')
                if options['autofix']:
                    group = Group.objects.create(name=group_name)
                else:
                    continue

            # Call all the permission currently on this group
            group_perms  =  { (p['content_type__app_label'], p['content_type__model'], p['codename']): p['id']
                              for p in group.permissions.all().values('content_type__app_label', 'content_type__model', 'codename', 'id')
                              if ((app_option and p['content_type__app_label'] == app_option) or (not app_option)) and
                              ((model_option and p['content_type__model'] == model_option) or (not model_option))}

            # Get all the permissions that should be on this group
            expected_perms = set(data for wildcard in perm_list for data in self.found_perms.enumerate(wildcard))
            group_perm_names = set(k for k in group_perms.keys())

            if group_perm_names == expected_perms:
                self.verbose(f'{group_name} already has the expected permissions')
                continue

            missing = expected_perms - group_perm_names
            extra = group_perm_names - expected_perms

            for app, model, perm_name in missing:
                if options['autofix']:
                    perm = Permission.objects.get_or_create(codename=f'{perm_name}_{model}', content_type=ContentType.objects.get(app_label=app, model=model))
                    self.vb(3, f'Creating {perm} for {app}.{model}')
                    group.permissions.add(perm)
                    self.vb(1, f'Adding {app} | {model} | {perm_name} to group {group_name}')
                else:
                    print(f'\'{app} | {model} | {perm_name}\' is missing from group {group_name}')

            for app, model, perm_name  in extra:
                if options['autofix']:
                    perm = group_perms[(app, model, perm_name)]
                    group.permissions.remove( perm)
                    self.vb(1, f'Removing {app} | {model} | {perm_name} - it is not needed in group {group_name}')
                else:
                    print(f'{app} | {model} | {perm_name} is additional in group {group_name}')


    def _check_permissions(self, app_option, model_option, options: dict[str, Any]):
        """Check that the appropriate permissions exist for the given models"""
        missing = []
        extra = []

        # Go through the model_permissions and check that the permissions exist
        for app, model, expected_perms in self.found_perms.items():
            if app_option and app != app_option:
                continue
            if model_option and model != model_option:
                continue

            try:
                ctype = ContentType.objects.get(app_label=app, model=model.lower())
            except ContentType.DoesNotExist:
                logger.error(f'Unable to find content type for {app}.{model}')
                continue

            # Get all of the permissions for this content type that exist
            all_perms = {p['codename']:p['id'] for p in Permission.objects.filter(content_type=ctype).values('id', 'codename')}

            all_codenames = set(codename for codename in all_perms)

            # Identifies and tracks missing/extra permissions for each model
            if all_codenames != expected_perms:

                missing_perms = expected_perms - all_codenames
                extra_perms = all_codenames - expected_perms

                missing.extend((app, model, perm) for perm in missing_perms)
                extra.extend((app, model, perm) for perm in extra_perms)

                for perm in missing_perms:
                    if options['autofix']:
                        p = Permission.objects.create(codename=f'{perm}', content_type=ctype, name=f'can {perm}')
                        self.vb(1, f'Adding {perm} to {app}.{model}')
                        self.found_perms[app][model].add(f'{perm}')
                    else:
                        self.found_perms[app][model].add(perm)
                        print(f'Would need to add {perm} to {app}.{model}')

                for perm in extra_perms:
                    if options['autofix']:
                        p = Permission.objects.filter(codename=f'{perm}', content_type=ctype)
                        p.delete()
                        self.vb(1, f'Removing {perm} from {app}.{model}')
                    else:
                        print(f'Would need to remove {perm} from {app}.{model}')

        if (missing or extra) and (self._verbose or not options['autofix']):
            print('\nMissing and Extra permissions')
            if missing:
                print('\n  Missing permissions:')
                for app, model_data in groupby(missing, lambda x: x[0]):
                    for model, perms in groupby(model_data, lambda x: x[1]):
                        print(f'    For {app} | {model}')
                        print(f'        Missing {','.join(f'{p[2]!r}' for p in perms)}')
                print('\n')
            else:
                print('    Nothing Missing')
            if extra:
                print('  Extra permissions:')
                for app, model_data in groupby(extra, lambda x: x[0]):
                    for model, perms in groupby(model_data, lambda x: x[1]):
                        print(f'    For {app} | {model}')
                        print(f'        Extras {','.join(f'{p[2]!r}' for p in perms)}')
            else:
                print('    Nothing Extra')
        else:
            if not missing:
                self.vb(2, 'No permissions missing')
        if not missing:
                self.vb(2, 'No extra permissions')


    def _identify_models_and_permissions(self, app_option, model_option, options: dict[str, Any]):
        """Enumerate all non-django apps and models, and identify the permissions that should exist"""
        for models in apps.get_models():
            app_name, model_name = models._meta.app_label, models._meta.model_name
            if models.__module__.startswith('django'):
                continue
            if model_name == 'UserExtended':
                continue

            special_perms = model_permissions.get(app_name, {}).get(model_name, [])

            if app_option and app_name != app_option:
               continue

            if model_option and model_name != model_option:
                continue

            self.found_perms[app_name][model_name] = set(f'{perm}_{model_name}' for perm in default_permissions)

            if special_perms:
                for p in special_perms:
                    # If there is a single '-' then remove all default permissions
                    if p == '-':
                        for default_perm in default_permissions:
                            self.found_perms[app_name][model_name].remove(f'{default_perm}_{model_name}')

                    # If permission starts with a '-' then remove it
                    if p.startswith('-') :
                        if f'{p[1:]}_{model_name}' in self.found_perms[app_name][model_name]:
                            self.found_perms[app_name][model_name].remove(f'{p[1:]}_{model_name}')
                    else:
                        self.found_perms[app_name][model_name].add(f'{p}_{model_name}')