"""Deployment and adversarial access checks for the approved group matrix."""
import json
from datetime import timedelta
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from Contributors.models import Contributor, Contributions
from GarageSale.access_policy import GROUP_NAMES, custom, require_template
from GarageSale.models import CommunicationTemplate, EventData
from user_management.models import TeamMember


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class AccessPolicyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        with TemporaryDirectory() as directory:
            call_command("sync_access_policy", apply=True, backup=Path(directory)/"initial.json", stdout=StringIO())
        cls.users = {}
        for name in GROUP_NAMES:
            user = get_user_model().objects.create_user(f"{name.lower()}@example.com", "password")
            user.groups.add(Group.objects.get(name=name))
            cls.users[name] = user
        cls.sponsor = Contributor.objects.create(contributor_type="Sponsor", contributor_name="Sponsor")
        cls.marketer = Contributor.objects.create(contributor_type="Marketer", contributor_name="Trader")
        today = timezone.localdate()
        cls.event = EventData.objects.create(use_from=today-timedelta(days=1), event_date=today+timedelta(days=30))

    def login(self, name):
        self.client.force_login(self.users[name])

    def test_anonymous_management_requests_redirect_to_login(self):
        from django.conf import settings
        from urllib.parse import parse_qs, urlsplit
        for route in ("TeamPages:Root", "Account:TransactionList", "GoogleDrive:status"):
            url = reverse(route)
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302)
            target = urlsplit(response.url)
            self.assertEqual(target.path, settings.LOGIN_URL)
            self.assertEqual(parse_qs(target.query)["next"], [url])

    def test_volunteer_has_profile_only_and_financier_has_independent_navigation(self):
        volunteer = self.users["Volunteer"]
        self.assertTrue(volunteer.has_perm(custom("manage_own_team_profile")))
        self.assertFalse(volunteer.has_perm(custom("access_team_pages")))
        financier = self.users["Financier"]
        self.assertTrue(financier.has_perm(custom("access_team_pages")))
        self.assertTrue(financier.has_perm("Accounts.upload_transaction"))
        self.assertFalse(financier.has_perm("GarageSale.view_eventdata"))
        self.assertFalse(financier.has_perm("Sponsors.view_sponsor"))
        self.login("Volunteer")
        self.assertEqual(self.client.get(reverse("TeamPages:Root")).status_code, 403)
        self.assertEqual(self.client.get(reverse("contributors:spreadsheet")).status_code, 403)

    def test_officers_gain_exec_membership_and_unique_financial_visibility(self):
        with TemporaryDirectory() as directory:
            call_command("sync_access_policy", apply=True, backup=Path(directory)/"officer.json", stdout=StringIO())
        officer = get_user_model().objects.get(pk=self.users["Officer"].pk)
        self.assertTrue(officer.groups.filter(name="ExecMember").exists())
        self.assertTrue(officer.has_perm("Accounts.view_transaction"))
        self.assertFalse(self.users["ExecMember"].has_perm("Accounts.view_transaction"))
        self.assertTrue(officer.has_perm("Sponsors.change_sponsor"))

    def test_prize_draw_manager_can_allocate_and_record_winners(self):
        manager = self.users["PrizeDrawManager"]
        self.assertEqual(manager.get_all_permissions(), {
            custom("access_team_pages"), custom("manage_own_team_profile"),
            "Contributors.view_prize_allocation", "Contributors.change_prize_allocation",
            "GarageSale.view_prizedrawwinner", "GarageSale.add_prizedrawwinner", "GarageSale.change_prizedrawwinner",
        })
        self.login("PrizeDrawManager")
        response = self.client.get(reverse("TeamPages:ContributionBoard", args=[self.event.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["can_edit"])
        self.assertEqual(self.client.get(reverse("contributors:spreadsheet")).status_code, 403)
        self.assertEqual(self.client.get(reverse("TeamPages:PrizeDrawWinners", args=[self.event.pk])).status_code, 200)

    def test_executives_and_officers_view_allocation_but_cannot_edit_or_record_winners(self):
        from GarageSale.models import PrizeDrawWinner
        prize = Contributions.objects.create(contributor=self.sponsor,event=self.event,cash=False,
                                             gift="Voucher",classification="prize_draw")
        allocation = reverse("TeamPages:ContributionBoard", args=[self.event.pk])
        winners = reverse("TeamPages:PrizeDrawWinners", args=[self.event.pk])
        for role in ("ExecMember", "Officer"):
            self.login(role)
            user = self.users[role]
            self.assertTrue(user.has_perm("Contributors.view_prize_allocation"))
            self.assertFalse(user.has_perm("Contributors.change_prize_allocation"))
            self.assertFalse(user.has_perm('GarageSale.add_prizedrawwinner'))
            self.assertFalse(user.has_perm('GarageSale.change_prizedrawwinner'))
            response = self.client.get(allocation)
            self.assertEqual(response.status_code,200)
            self.assertFalse(response.context['can_edit'])
            self.assertEqual(self.client.post(allocation).status_code,403)
            self.assertEqual(self.client.post(winners, json.dumps({"action":"ticket","contribution_id":prize.pk,
                "revision":"new","ticket_number":"123"}),content_type="application/json").status_code,403)
        self.assertFalse(PrizeDrawWinner.objects.exists())

    def test_prize_draw_manager_can_save_allocation_and_two_stage_winner(self):
        from GarageSale.models import PrizeDrawWinner
        prize = Contributions.objects.create(contributor=self.sponsor,event=self.event,cash=False,gift='Voucher')
        self.login('PrizeDrawManager')
        board = reverse('TeamPages:ContributionBoard',args=[self.event.pk])
        revision = self.client.get(board).context['revision']
        result = self.client.post(board,json.dumps({'revision':revision,
            'columns':{'unclassified':[],'prize_draw':[prize.pk],'tombola':[]}}),content_type='application/json')
        self.assertEqual(result.status_code,200)
        winner_url = reverse('TeamPages:PrizeDrawWinners',args=[self.event.pk])
        ticket = self.client.post(winner_url,json.dumps({'action':'ticket','revision':'new',
            'contribution_id':prize.pk,'ticket_number':'00012'}),content_type='application/json')
        self.assertEqual(ticket.status_code,200)
        details = self.client.post(winner_url,json.dumps({'action':'details','revision':ticket.json()['winner']['revision'],
            'contribution_id':prize.pk,'name':'Sample Winner','phone':'','address':''}),content_type='application/json')
        self.assertEqual(details.status_code,200)
        self.assertEqual(PrizeDrawWinner.objects.get(contribution=prize).name,'Sample Winner')

    def test_other_operational_groups_do_not_gain_prize_allocation(self):
        url = reverse("TeamPages:ContributionBoard", args=[self.event.pk])
        for name in ("SponsorshipManager", "CraftMarketManager", "Financier", "Volunteer"):
            with self.subTest(group=name):
                user = self.users[name]
                self.assertFalse(user.has_perm("Contributors.view_prize_allocation"))
                self.assertFalse(user.has_perm("Contributors.change_prize_allocation"))
                self.login(name)
                self.assertEqual(self.client.get(url).status_code, 403)

    def test_sync_renames_old_prize_role_and_retains_membership(self):
        legacy = Group.objects.create(name='PrizeAllocationManager')
        member = get_user_model().objects.create_user('legacy-draw@example.com', 'password')
        member.groups.add(legacy)
        with TemporaryDirectory() as directory:
            call_command('sync_access_policy', apply=True, backup=Path(directory)/'rename.json', stdout=StringIO())
        member = get_user_model().objects.get(pk=member.pk)
        self.assertFalse(Group.objects.filter(name='PrizeAllocationManager').exists())
        self.assertTrue(member.groups.filter(name='PrizeDrawManager').exists())
        self.assertTrue(member.has_perm('GarageSale.add_prizedrawwinner'))
        self.assertFalse(member.groups.filter(name='ExecMember').exists())

    def test_domain_managers_cannot_read_or_edit_other_contributor_type(self):
        self.login("SponsorshipManager")
        spreadsheet = self.client.get(reverse("contributors:spreadsheet"))
        self.assertEqual(spreadsheet.context["addable_contributor_types"], ["Sponsor"])
        self.assertContains(spreadsheet, '<option value="Sponsor">')
        self.assertNotContains(spreadsheet, '<option value="Marketer">')
        self.assertEqual(self.client.get(reverse("contributors:details", args=[self.marketer.pk])).status_code, 403)
        response = self.client.post(reverse("contributors:spreadsheet_save", args=[self.marketer.pk]),
                                    data=json.dumps({"contact_name": "Forbidden"}), content_type="application/json")
        self.assertEqual(response.status_code, 403)
        self.marketer.refresh_from_db()
        self.assertNotEqual(self.marketer.contact_name, "Forbidden")
        self.login("CraftMarketManager")
        self.assertEqual(self.client.get(reverse("contributors:details", args=[self.sponsor.pk])).status_code, 403)

    def test_csv_exports_are_type_scoped(self):
        self.login("SponsorshipManager")
        response = self.client.get(reverse("contributors:download"))
        self.assertContains(response, "Sponsor")
        self.assertNotContains(response, "Trader")
        self.assertEqual(self.client.get(reverse("contributors:download"), {"contributor_type": "Marketer"}).status_code, 403)

    def test_import_rejects_foreign_type_before_saving_any_changes(self):
        self.login("SponsorshipManager")
        response = self.client.post(reverse("contributors:upload"), {
            "stage": "review_changes", "contributor_type": "Sponsor",
            "csv_data": json.dumps([{"Name": "New sponsor"}, {"Name": "Trader"}]),
            "column_mapping": json.dumps({"Name": "contributor_name"}),
        })
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Contributor.objects.filter(contributor_name="New sponsor").exists())

    @override_settings(APPS_SETTINGS={"Sponsors": {"EmailTemplateCategory": "SponsorLetters"},
                                     "CraftMarket": {"EmailTemplateCategory": "MarketLetters"}})
    def test_template_categories_and_delete_permissions(self):
        sponsor = self.users["SponsorshipManager"]
        require_template(sponsor, "SponsorLetters", "change")
        with self.assertRaises(PermissionDenied):
            require_template(sponsor, "MarketLetters", "view")
        with self.assertRaises(PermissionDenied):
            require_template(sponsor, "SponsorLetters", "delete")
        template = CommunicationTemplate.objects.create(category="MarketLetters", subject="Hidden", html_content="Hidden", use_from=timezone.localdate())
        self.login("SponsorshipManager")
        self.assertEqual(self.client.get(reverse("TeamPages:CommunicationTemplateEdit", args=[template.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse("TeamPages:CommunicationTemplateDuplicate", args=[template.pk])).status_code, 403)

    def test_financier_cannot_delete_transactions_and_exec_cannot_view_raw_data(self):
        self.login("Financier")
        self.assertEqual(self.client.put(reverse("Account:delete_transaction", args=[999])).status_code, 403)
        self.login("ExecMember")
        self.assertEqual(self.client.get(reverse("Account:TransactionList")).status_code, 403)
        self.assertEqual(self.client.get(reverse("GoogleDrive:status")).status_code, 403)

    def test_profile_owner_and_other_profile_boundaries(self):
        member = TeamMember.objects.create(user=self.users["Volunteer"], role="Volunteer")
        other = TeamMember.objects.create(user=self.users["Financier"], role="Treasurer")
        self.login("Volunteer")
        self.assertEqual(self.client.get(reverse("user_management:profile", args=[member.team_member_id])).status_code, 200)
        self.assertEqual(self.client.get(reverse("user_management:profile", args=[other.team_member_id])).status_code, 403)
        self.assertEqual(self.client.get(reverse("user_management:profile_edit", args=[other.team_member_id])).status_code, 403)
        self.login("ExecMember")
        self.assertEqual(self.client.get(reverse("user_management:profile_edit", args=[other.team_member_id])).status_code, 403)

    def test_deleting_donations_requires_webadmin(self):
        contribution = Contributions.objects.create(contributor=self.sponsor, event=self.event, gift="Hamper")
        self.login("SponsorshipManager")
        response = self.client.post(reverse("contributors:delete_contribution", args=[self.sponsor.pk, contribution.pk]),
                                    {"event_id": self.event.pk})
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Contributions.objects.filter(pk=contribution.pk).exists())

    def test_report_is_read_only_and_apply_is_repeatable_preserving_libraries(self):
        ct, _ = ContentType.objects.get_or_create(app_label="third_party", model="widget")
        library = Permission.objects.create(content_type=ct, codename="view_widget", name="View widget")
        group = Group.objects.get(name="WebAdmin")
        group.permissions.add(library)
        before = list(Permission.objects.order_by("pk").values())
        call_command("sync_access_policy", stdout=StringIO())
        self.assertEqual(list(Permission.objects.order_by("pk").values()), before)
        with TemporaryDirectory() as directory:
            first, second = Path(directory)/"first.json", Path(directory)/"second.json"
            call_command("sync_access_policy", apply=True, backup=first, stdout=StringIO())
            grants = list(group.permissions.order_by("pk").values_list("pk", flat=True))
            call_command("sync_access_policy", apply=True, backup=second, stdout=StringIO())
            self.assertEqual(list(group.permissions.order_by("pk").values_list("pk", flat=True)), grants)
        self.assertTrue(group.permissions.filter(pk=library.pk).exists())
        self.assertFalse(get_user_model().objects.filter(is_superuser=True).exists())

    def test_alias_direct_grants_survive_and_snapshot_can_restore(self):
        ct = ContentType.objects.get(app_label="GarageSale", model="eventdata")
        alias = Permission.objects.create(content_type=ct, codename="change_event", name="Old edit event")
        user = self.users["Volunteer"]
        user.user_permissions.add(alias)
        with TemporaryDirectory() as directory:
            snapshot, rollback = Path(directory)/"before.json", Path(directory)/"rollback.json"
            call_command("sync_access_policy", apply=True, backup=snapshot, stdout=StringIO())
            self.assertFalse(Permission.objects.filter(pk=alias.pk).exists())
            self.assertTrue(user.user_permissions.filter(codename="change_eventdata").exists())
            call_command("sync_access_policy", apply=True, restore=snapshot, backup=rollback, stdout=StringIO())
            self.assertTrue(user.user_permissions.filter(codename="change_event").exists())

    def test_direct_retired_roles_require_review_not_automatic_privilege_conversion(self):
        ct, _ = ContentType.objects.get_or_create(app_label="GarageSale", model="general")
        flag = Permission.objects.create(content_type=ct, codename="is_trustee", name="Old role")
        self.users["Volunteer"].user_permissions.add(flag)
        with TemporaryDirectory() as directory:
            snapshot = Path(directory)/"blocked.json"
            with self.assertRaisesMessage(CommandError, "Resolve the direct retired role"):
                call_command("sync_access_policy", apply=True, backup=snapshot, stdout=StringIO())
            self.assertFalse(snapshot.exists())
        self.assertTrue(Permission.objects.filter(pk=flag.pk).exists())

    def test_new_officer_membership_and_removal_preserve_exec_invariant(self):
        officer = self.users["Officer"]
        self.assertTrue(officer.groups.filter(name="ExecMember").exists())
        officer.groups.remove(Group.objects.get(name="ExecMember"))
        self.assertTrue(officer.groups.filter(name="ExecMember").exists())
        Group.objects.get(name="ExecMember").user_set.clear()
        self.assertTrue(officer.groups.filter(name="ExecMember").exists())

    def test_clearing_exec_members_retains_only_officers(self):
        executive = Group.objects.get(name="ExecMember")
        ordinary = self.users["ExecMember"]
        officer = self.users["Officer"]
        self.assertTrue(ordinary.groups.filter(pk=executive.pk).exists())
        executive.user_set.clear()
        self.assertTrue(officer.groups.filter(pk=executive.pk).exists())
        self.assertFalse(ordinary.groups.filter(pk=executive.pk).exists())

    def test_rollback_can_restore_pre_policy_officer_memberships_exactly(self):
        from user_management.permission_signals import restoring_memberships
        user = self.users["Officer"]
        token = restoring_memberships.set(True)
        try:
            user.groups.remove(Group.objects.get(name="ExecMember"))
        finally:
            restoring_memberships.reset(token)
        with TemporaryDirectory() as directory:
            snapshot, rollback = Path(directory)/"before.json", Path(directory)/"rollback.json"
            call_command("sync_access_policy", apply=True, backup=snapshot, stdout=StringIO())
            self.assertTrue(user.groups.filter(name="ExecMember").exists())
            call_command("sync_access_policy", apply=True, restore=snapshot, backup=rollback, stdout=StringIO())
            self.assertTrue(user.groups.filter(name="Officer").exists())
            self.assertFalse(user.groups.filter(name="ExecMember").exists())
