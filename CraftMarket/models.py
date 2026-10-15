"""Compatibility imports for historical Craft Market tables and migrations.

The active trader data lives in Contributors.models. Keep the original ORM model
names and upload callable import path until the legacy tables are removed by migration.
"""
# TODO(legacy-removal): Remove these exports with the legacy tables after migration compatibility is retired.
from .legacy_models import LegacyHistory, LegacyMarketer, LegacyMarketerState, save_logo_to

# Historical migration and Django model identities; use Legacy* names in runtime code.
History = LegacyHistory
Marketer = LegacyMarketer
MarketerState = LegacyMarketerState
