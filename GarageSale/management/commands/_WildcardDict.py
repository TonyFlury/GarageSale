import re
from collections import defaultdict
from functools import partial
from typing import Generator, Any

from django.core.management import CommandError
import logging

class WildcardDict:
    def __init__(self, d=None):
        if d is None:
            d = {}
        self.__dict__ = defaultdict(partial(defaultdict,set))
        for a, m in d.items():
            for model_name, perms in m.items():
                self[a][model_name] = perms

    def items(self):
        for app, model in self.__dict__.items():
            for model_name, perms in model.items():
                yield app, model_name, perms
    def __getitem__(self, key):
        return self.__dict__[key]

    def __setitem__(self, key, value):
        return self.__dict__.__setitem__(key, value)

    def __missing__(self, key):
        self[key] = {}

    @staticmethod
    def _parse_qualifier(wildcard:str) -> tuple[str, set]:

        ignore = set()

        if wildcard.startswith('*:') and wildcard.find(':') == 1:
            wildcard, qualifier = wildcard.split(':')
            m = re.match(r'([A-Za-z]+?)\((.+)\)', qualifier)
            match m and m.group(1):
                case 'not':
                    ignore = set(m.group(2).split(','))
                case None:
                    raise CommandError(f'Invalid qualifier {qualifier} in {wildcard}')
        return wildcard, ignore

    @staticmethod
    def _match_wildcard(wildcard:tuple[str,set[str]], value:str) -> bool:
        return (wildcard[0] == '*' or value == wildcard[0]) and (value not in wildcard[1])

    def enumerate(self, wildcard:str) -> Generator[tuple[str,str,str], None, None]:
        wilds = [self._parse_qualifier(i) for i in  (wildcard.split('|') if '|' in wildcard else [wildcard,'*','*']) ]
        app_wildcard, model_wildcard, perm_wildcard = wilds

        for app, models in self.__dict__.items():
            if not self._match_wildcard(app_wildcard, app):
                continue

            for model, perms in models.items():
                if not self._match_wildcard(model_wildcard, model):
                    continue

                for name in perms:
                    if self._match_wildcard(perm_wildcard, name):
                        yield app, model, name
