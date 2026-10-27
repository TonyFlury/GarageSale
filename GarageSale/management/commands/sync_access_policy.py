"""Preview/apply the agreed groups with a portable, private rollback snapshot."""
import json
import os
from pathlib import Path

from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.auth.management import create_permissions
from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from GarageSale.access_policy import ALIASES, GROUP_NAMES, GROUP_PERMISSIONS, GROUP_RENAMES, PROJECT_APPS, ROLE_FLAGS


def key(permission):
    return f"{permission.content_type.app_label}.{permission.codename}"


class Command(BaseCommand):
    help = "Report the agreed access-policy changes; use --apply --backup FILE to deploy them."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--backup", type=Path, help="New private JSON snapshot file, required when applying.")
        parser.add_argument("--restore", type=Path, help="Restore a snapshot's project grants and group memberships.")
        parser.add_argument("--dry-run", action="store_true", help="Explicit spelling of the default read-only report.")

    def handle(self, *args, **options):
        if options["apply"] and options["dry_run"]:
            raise CommandError("Choose --apply or --dry-run, not both.")
        if options["restore"]:
            if not options["apply"]:
                raise CommandError("Snapshot restoration requires --apply --backup NEW_FILE.")
            return self.restore(options)
        if options["apply"] and not options["backup"]:
            raise CommandError("--apply requires --backup FILE.")
        permissions = list(Permission.objects.select_related("content_type").filter(content_type__app_label__in=PROJECT_APPS))
        direct_roles = get_user_model().objects.filter(user_permissions__in=[p for p in permissions if key(p) in ROLE_FLAGS]).distinct()
        unknown_roles = Group.objects.filter(permissions__in=[p for p in permissions if key(p) in ROLE_FLAGS]).exclude(name__in=GROUP_NAMES).distinct()
        for user in direct_roles:
            self.stdout.write(f"REVIEW direct retired role flag: {user.email}. Assign reviewed groups and remove the direct role flag before applying.")
        for group in unknown_roles:
            self.stdout.write(f"REVIEW retired role flags on unmanaged group: {group.name}.")
        for user in get_user_model().objects.filter(groups__name="WebAdmin", is_staff=False):
            self.stdout.write(f"ADMIN ACCESS: {user.email} is not staff; explicitly enable staff access if Django admin is required.")
        for previous, current in GROUP_RENAMES.items():
            if Group.objects.filter(name=previous).exists():
                self.stdout.write(f"Rename responsibility group: {previous} -> {current}; existing memberships retained.")
        for name in GROUP_NAMES:
            group = Group.objects.filter(name=name).first()
            current = {key(p) for p in group.permissions.filter(content_type__app_label__in=PROJECT_APPS).select_related("content_type")} if group else set()
            expected = GROUP_PERMISSIONS.get(name, set()) if name != "WebAdmin" else {
                key(p) for p in permissions if key(p) not in ROLE_FLAGS | set(ALIASES)}
            self.stdout.write(f"{name}: add {sorted(expected-current)}; remove {sorted(current-expected)}")
        officer_count = get_user_model().objects.filter(groups__name="Officer").exclude(groups__name="ExecMember").count()
        self.stdout.write(f"Officer users to add to ExecMember: {officer_count}.")
        for user in get_user_model().objects.filter(user_permissions__content_type__app_label__in=PROJECT_APPS).distinct():
            self.stdout.write(f"Preserving/reconciling direct project grants: {user.email}")
        if not options["apply"]:
            self.stdout.write("Read-only report. Third-party grants and staff/superuser flags are excluded.")
            return
        if direct_roles.exists() or unknown_roles.exists():
            raise CommandError("Resolve the direct retired role flags listed above before applying; no changes made.")
        self.backup(options["backup"])
        with transaction.atomic():
            self.rename_groups()
            for config in apps.get_app_configs():
                if config.label in PROJECT_APPS:
                    create_permissions(config, verbosity=0)
            self.merge_aliases()
            catalog = list(Permission.objects.filter(content_type__app_label__in=PROJECT_APPS).select_related("content_type"))
            by_key = {key(p): p for p in catalog}
            needed = set().union(*GROUP_PERMISSIONS.values())
            missing = needed - by_key.keys()
            if missing:
                raise CommandError(f"Missing declared permissions: {sorted(missing)}. Run migrate first.")
            for name in GROUP_NAMES:
                group, _ = Group.objects.get_or_create(name=name)
                expected = set(by_key) if name == "WebAdmin" else GROUP_PERMISSIONS[name]

                # Only first-party grants are reconciled. Library/Django admin
                # grants are never passed to set(), removed or inferred here.
                group.permissions.remove(*[p for p in catalog if key(p) not in expected])
                group.permissions.add(*[by_key[code] for code in expected])
            executive = Group.objects.get(name="ExecMember")
            for user in get_user_model().objects.filter(groups__name="Officer"):
                user.groups.add(executive)
        self.stdout.write(self.style.SUCCESS("Access policy applied. Third-party grants and staff/superuser flags unchanged."))

    @staticmethod
    def rename_groups():
        """Retain memberships and third-party grants when a responsibility is renamed."""
        for previous, current in GROUP_RENAMES.items():
            old = Group.objects.filter(name=previous).first()
            # Sites installed after the rename have nothing to transfer.
            if old is None:
                continue
            target = Group.objects.filter(name=current).first()
            # A straight rename preserves the original group's ID and memberships.
            if target is None:
                old.name = current
                old.save(update_fields=['name'])
            else:
                target.permissions.add(*old.permissions.all())
                target.user_set.add(*old.user_set.all())
                old.delete()

    def backup(self, path):
        if path is None:
            raise CommandError("A new --backup FILE is required.")
        data = {"format": "garagesale-access-v1", "permissions": [], "groups": [], "users": []}
        for p in Permission.objects.filter(content_type__app_label__in=PROJECT_APPS).select_related("content_type"):
            data["permissions"].append({"app": p.content_type.app_label, "model": p.content_type.model, "codename": p.codename, "name": p.name})
        for group in Group.objects.all():
            data["groups"].append({"name": group.name, "permissions": list(group.permissions.filter(content_type__app_label__in=PROJECT_APPS).values_list("content_type__app_label", "content_type__model", "codename"))})
        for user in get_user_model().objects.all():
            data["users"].append({"email": user.email, "groups": list(user.groups.values_list("name", flat=True)),
                                  "permissions": list(user.user_permissions.filter(content_type__app_label__in=PROJECT_APPS).values_list("content_type__app_label", "content_type__model", "codename"))})
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w") as destination:
                json.dump(data, destination, indent=2)
        except OSError as error:
            raise CommandError(f"Cannot create backup: {error}") from error

    @staticmethod
    def merge_aliases():
        for p in list(Permission.objects.filter(content_type__app_label__in=PROJECT_APPS).select_related("content_type")):
            code = key(p)
            if code in ALIASES:
                app, codename = ALIASES[code].split(".", 1)
                target = Permission.objects.get(content_type__app_label=app, codename=codename)
                for group in p.group_set.all():
                    group.permissions.add(target)
                for user in p.user_set.all():
                    user.user_permissions.add(target)
                p.delete()
            elif code in ROLE_FLAGS:
                p.delete()

    def restore(self, options):
        from django.contrib.contenttypes.models import ContentType
        try:
            data = json.loads(options["restore"].read_text())
            if data["format"] != "garagesale-access-v1":
                raise ValueError("Wrong snapshot format")
            if any(p["app"] not in PROJECT_APPS for p in data["permissions"]):
                raise ValueError("Snapshot contains non-project permissions")
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise CommandError(f"Invalid snapshot: {error}") from error
        self.backup(options["backup"])
        with transaction.atomic():
            for p in data["permissions"]:
                ct, _ = ContentType.objects.get_or_create(app_label=p["app"], model=p["model"])
                Permission.objects.get_or_create(content_type=ct, codename=p["codename"], defaults={"name": p["name"]})
            def resolve(values):
                return [Permission.objects.get(content_type__app_label=a, content_type__model=m, codename=c) for a,m,c in values]
            for entry in data["groups"]:
                group, _ = Group.objects.get_or_create(name=entry["name"])
                group.permissions.remove(*group.permissions.filter(content_type__app_label__in=PROJECT_APPS))
                group.permissions.add(*resolve(entry["permissions"]))
            original_groups = {entry["name"] for entry in data["groups"]}
            for group in Group.objects.filter(name__in=set(GROUP_NAMES)-original_groups):
                group.permissions.remove(*group.permissions.filter(content_type__app_label__in=PROJECT_APPS))
            for entry in data["users"]:
                user = get_user_model().objects.get(email=entry["email"])
                user.user_permissions.remove(*user.user_permissions.filter(content_type__app_label__in=PROJECT_APPS))
                user.user_permissions.add(*resolve(entry["permissions"]))
                # Rollback must reproduce the old memberships exactly, even if
                # the old installation did not yet enforce Officer inheritance.
                from user_management.permission_signals import restoring_memberships
                token = restoring_memberships.set(True)
                try:
                    user.groups.set(Group.objects.filter(name__in=entry["groups"]))
                finally:
                    restoring_memberships.reset(token)
        self.stdout.write(self.style.SUCCESS("Snapshot grants restored; deploy the matching application revision when rolling back."))
