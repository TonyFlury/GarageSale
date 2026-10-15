from datetime import timedelta
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from Contributors.models import Contributor, ContributorEvent, ContributorHistory, Contributions
from CraftMarket.views import MarketerSpreadsheetView, MarketEntryPoint
from CraftMarket.rsvp import ContributorRSVP, invitation_url
from GarageSale.models import CommunicationTemplate, EventData, TemplateAttachment


@override_settings(APPS_SETTINGS={"CraftMarket": {
    "EmailTemplateCategory": "MarketTest", "EmailFrom": "market@example.com",
}})
class MarketSpreadsheetTests(TestCase):
    def setUp(self):
        today = timezone.localdate()
        self.event = EventData.objects.create(event_date=today + timedelta(days=30), use_from=today - timedelta(days=1))
        self.previous = EventData.objects.create(event_date=today - timedelta(days=60), use_from=today - timedelta(days=90))
        self.user = get_user_model().objects.create_user(email="market-team@example.com", password="test-password")
        self.user.user_permissions.add(*Permission.objects.filter(
            content_type__app_label="CraftMarket", codename__in=["suggest_marketer", "change_marketer"],
        ))
        self.marketer = Contributor.objects.create(contributor_type="Marketer", contributor_name="Oak & Co",
                                                   contact_name="Alex", email="alex@example.com")
        self.other = Contributor.objects.create(contributor_type="Marketer", contributor_name="Birch", email="")
        self.sponsor = Contributor.objects.create(contributor_type="Sponsor", contributor_name="Sponsor")
        self.templates = {}
        for sub_category in ("Invited", "Confirmed", "Newsletter", "Terms"):
            self.templates[sub_category] = CommunicationTemplate.objects.create(
                category="MarketTest", sub_category=sub_category, summary=sub_category,
                subject="Hello {{ trading_name }}", html_content="Hello {{ contact_name }}", use_from=today,
            )

    def view(self, data=None, event=None, method="post", **kwargs):
        request = getattr(RequestFactory(), method)(reverse("CraftMarket:EntryPoint"), data or {})
        request.user = self.user
        request.current_event = event or self.event
        view = MarketerSpreadsheetView()
        view.setup(request, **kwargs)
        return view

    def action(self, status, delivery=None, template=None, ids=None, **extra):
        data = {"selected_contributor": ids or [str(self.marketer.pk)], **extra}
        if delivery:
            data["delivery"] = delivery
        if template:
            data["email_template_id"] = str(template.pk)
        view = self.view(data)
        view._action(view.request.POST, status)
        return view

    def record_status(self, status, marketer=None, event=None, **kwargs):
        return ContributorEvent.objects.create(contributor=marketer or self.marketer,
                                              event=event or self.event, status=status, **kwargs)

    def test_entry_point_renders_contacts_and_status_without_contributions(self):
        view = self.view(method="get")
        response = MarketEntryPoint.as_view()(view.request)
        response.render()
        self.assertContains(response, "Record contact with Oak &amp; Co")
        self.assertContains(response, '<th class="extra-column">Status</th>', html=True)
        self.assertContains(response, 'data-show-contributions="false"')
        self.assertNotIn(self.sponsor, response.context_data["contributors"])
        self.assertFalse(response.context_data["show_contributions"])

    def test_filters_use_latest_status_for_current_event(self):
        self.record_status("Confirmed", event=self.previous)
        self.record_status("Invited")
        self.record_status("Rejected")
        for status, expected in (("none", [self.other]), ("invited", []),
                                 ("confirmed", []), ("rejected", [self.marketer])):
            with self.subTest(status=status):
                view = self.view({"selected_filters": status}, method="get")
                self.assertEqual(list(view.get_queryset()), expected)
        self.assertEqual(list(self.view({"selected_filters": "confirmed"}, method="get",
                                        event_id=self.previous.pk).get_queryset()), [self.marketer])

    def test_none_includes_null_blank_and_explicit_none(self):
        for status in (None, "", "None"):
            self.record_status(status)
            view = self.view({"selected_filters": "none"}, method="get")
            self.assertEqual(set(view.get_queryset()), {self.marketer, self.other})

    def test_contact_filters_use_comments_after_previous_event(self):
        ContributorHistory.objects.create(contributor=self.marketer, event_category="Contact", event_type="Comment",
                                          details="Called", timestamp=timezone.now())
        ContributorHistory.objects.create(contributor=self.other, event_category="Contact", event_type="Comment",
                                          details="Old call", timestamp=timezone.now() - timedelta(days=61))
        for name, expected in (("contacted", [self.marketer]), ("not_contacted", [self.other])):
            self.assertEqual(list(self.view({"selected_filters": name}, method="get").get_queryset()), expected)
        self.record_status("Invited")
        self.assertEqual(list(self.view({"selected_filters": ["contacted", "invited"]}, method="get").get_queryset()),
                         [self.marketer])

    def test_status_chooser_does_not_change_status_and_offers_optional_email(self):
        for status in ("Invited", "Confirmed"):
            if status == "Confirmed":
                self.record_status("Invited")
            before = ContributorEvent.objects.count()
            view = self.action(status, selected_filters=["contacted"])
            self.assertIn('type="checkbox" name="delivery" value="send_email"', view.modal_html)
            self.assertIn('name="confirm_action" value="1"', view.modal_html)
            self.assertNotIn('Save ', view.modal_html)
            self.assertIn(f'<option value="{self.templates[status].pk}">', view.modal_html)
            self.assertIn('name="selected_filters" value="contacted"', view.modal_html)
            self.assertIn(f'name="market_event_id" value="{self.event.pk}"', view.modal_html)
            self.assertEqual(ContributorEvent.objects.count(), before)

    @patch("CraftMarket.spreadsheet.CommunicationTemplate.send_email", return_value=1)
    def test_optional_email_does_not_run_when_saving_without_email(self, send):
        for status in ("Invited", "Confirmed"):
            self.action(status, "without_email", template=self.templates[status])
            latest = self.marketer.contributorevent_set.latest("pk")
            self.assertEqual(latest.status, status)
            self.assertEqual(latest.event, self.event)
            self.assertEqual(latest.user, self.user)
        send.assert_not_called()
        self.assertFalse(Contributions.objects.exists())

    def test_missing_templates_still_allow_status_without_email(self):
        CommunicationTemplate.objects.all().delete()
        view = self.action("Invited")
        self.assertIn("No email templates", view.modal_html)
        self.assertIn('value="1">Invite</button>', view.modal_html)
        self.action("Invited", "without_email")
        self.assertEqual(self.marketer.contributorevent_set.get().status, "Invited")

    @patch("CraftMarket.spreadsheet.CommunicationTemplate.send_email", return_value=1)
    def test_status_and_general_email_use_separate_template_categories(self, send):
        for status in ("Invited", "Confirmed"):
            self.action(status, "send_email", self.templates[status])
        self.action(None, "send_email", self.templates["Newsletter"])
        self.assertEqual(send.call_count, 3)
        self.assertEqual(ContributorEvent.objects.count(), 2)
        context = send.call_args.kwargs["context"]
        self.assertEqual(context["from"], "market@example.com")
        self.assertEqual(context["email"], ["alex@example.com"])
        self.assertEqual(context["trading_name"], "Oak & Co")
        self.assertEqual(context["contact_name"], "Alex")
        self.assertNotIn("donation", context)

    @patch("CraftMarket.spreadsheet.CommunicationTemplate.send_email", return_value=1)
    def test_invite_email_contains_absolute_personalised_rsvp_url(self, send):
        self.action("Invited", "send_email", self.templates["Invited"])
        url = send.call_args.kwargs["context"]["url"]
        self.assertTrue(url.startswith("http://testserver/"))
        from urllib.parse import urlsplit
        from django.urls import resolve
        match = resolve(urlsplit(url).path)
        self.assertEqual(match.view_name, "CraftMarket:ContributorRSVP")
        response = ContributorRSVP.as_view()(self.factory_request(), **match.kwargs)
        self.assertEqual(response.context_data["form_section"], "portal_login")

    def factory_request(self, data=None, session=None):
        request = RequestFactory().post('/', data) if data is not None else RequestFactory().get('/')
        request.session = session if session is not None else {}
        return request

    @patch("CraftMarket.spreadsheet.CommunicationTemplate.send_email", return_value=1)
    def test_rsvp_requires_email_and_records_response_against_invited_event(self, send):
        from urllib.parse import urlsplit
        from django.urls import resolve
        self.action("Invited", "without_email")
        url = invitation_url(self.factory_request(), self.marketer, self.event)
        kwargs = resolve(urlsplit(url).path).kwargs
        session = {}
        def post(data):
            return ContributorRSVP.as_view()(self.factory_request(data, session), **kwargs)

        response = post({'form_section': 'accept_reject', 'RSVP_Yes': 'yes'})
        self.assertEqual(response.context_data['form_section'], 'portal_login')
        response = post({'form_section': 'portal_login', 'email': 'wrong@example.com'})
        self.assertTrue(response.context_data['form'].errors)
        response = post({'form_section': 'portal_login', 'email': self.marketer.email})
        self.assertEqual(response.context_data['form_section'], 'accept_reject')
        # A submitted ID must never select another trader.
        response = post({'form_section': 'accept_reject', 'RSVP_Yes': 'yes', 'marketer_id': self.other.pk})
        self.assertEqual(response.context_data['form_section'], 'accept')
        self.assertEqual(self.marketer.contributorevent_set.latest('pk').status, 'Confirmed')
        self.assertFalse(self.other.contributorevent_set.exists())
        self.assertEqual(send.call_count, 1)
        self.assertIn('error', post({'form_section': 'accept_reject', 'RSVP_Yes': 'yes'}).context_data)

    def test_rsvp_rejects_tampered_links_and_links_superseded_by_new_invites(self):
        from urllib.parse import urlsplit
        from django.urls import resolve
        self.action('Invited', 'without_email')
        url = invitation_url(self.factory_request(), self.marketer, self.event)
        kwargs = resolve(urlsplit(url).path).kwargs
        response = ContributorRSVP.as_view()(self.factory_request(), token=kwargs['token'] + 'x')
        self.assertIn('error', response.context_data)
        ContributorEvent.objects.create(contributor=self.marketer, event=self.event, status='Invited')
        response = ContributorRSVP.as_view()(self.factory_request(), **kwargs)
        self.assertIn('error', response.context_data)

    def test_rsvp_rejection_and_non_invited_email_context(self):
        from urllib.parse import urlsplit
        from django.urls import resolve
        self.assertEqual(invitation_url(self.factory_request(), self.marketer, self.event), '')
        self.action('Invited', 'without_email')
        kwargs = resolve(urlsplit(invitation_url(self.factory_request(), self.marketer, self.event)).path).kwargs
        session = {}
        ContributorRSVP.as_view()(self.factory_request(
            {'form_section': 'portal_login', 'email': self.marketer.email}, session), **kwargs)
        response = ContributorRSVP.as_view()(self.factory_request(
            {'form_section': 'accept_reject', 'RSVP_No': 'no'}, session), **kwargs)
        self.assertEqual(response.context_data['form_section'], 'reject')
        self.assertEqual(self.marketer.contributorevent_set.latest('pk').status, 'Rejected')
        self.assertEqual(invitation_url(self.factory_request(), self.marketer, self.event), '')

    def test_template_selection_excludes_wrong_subcategories_attachments_and_future_versions(self):
        self.templates["Terms"].sub_category = "Confirmed"
        self.templates["Terms"].save(update_fields=["sub_category"])
        TemplateAttachment.objects.create(template=self.templates["Confirmed"], upload=False,
                                          template_name=self.templates["Terms"].summary)
        CommunicationTemplate.objects.create(category="MarketTest", sub_category="Invited", summary="Future",
                                             subject="Future", html_content="Future", use_from=timezone.localdate() + timedelta(days=1))
        CommunicationTemplate.objects.create(category="Other", sub_category="Newsletter", summary="Wrong category",
                                             subject="Other", html_content="Other", use_from=timezone.localdate())
        view = self.view()
        self.assertEqual(view._available_templates("Invited"), [self.templates["Invited"]])
        self.assertEqual(view._available_templates("Confirmed"), [self.templates["Confirmed"]])
        self.assertEqual(view._available_templates(), [self.templates["Newsletter"]])
        chooser = self.action(None)
        self.assertNotIn(f'<option value="{self.templates["Invited"].pk}">', chooser.modal_html)
        self.assertNotIn(f'<option value="{self.templates["Confirmed"].pk}">', chooser.modal_html)

    @patch("CraftMarket.spreadsheet.CommunicationTemplate.send_email")
    def test_invalid_or_multiple_templates_do_not_change_status_or_send(self, send):
        for template_ids in ([], ["999999"], [str(self.templates["Confirmed"].pk)],
                             [str(self.templates["Invited"].pk)] * 2):
            view = self.action("Invited", "send_email", email_template_id=template_ids)
            self.assertIn('role="alert"', view.modal_html)
            self.assertFalse(ContributorEvent.objects.exists())
        send.assert_not_called()

    def test_invalid_or_cross_type_selections_do_not_partially_save(self):
        for ids in (["invalid"], [str(self.marketer.pk), str(self.sponsor.pk)],
                    [str(self.marketer.pk), "999999"]):
            view = self.action("Invited", "without_email", ids=ids)
            self.assertIn('role="alert"', view.modal_html)
            self.assertFalse(ContributorEvent.objects.exists())

    def test_duplicate_recipient_ids_create_one_status(self):
        self.action("Invited", "without_email", ids=[str(self.marketer.pk)] * 2)
        self.assertEqual(ContributorEvent.objects.count(), 1)

    def test_invalid_and_stale_status_transitions_do_not_save(self):
        view = self.action("Confirmed", "without_email")
        self.assertIn("must have status Invited", view.modal_html)
        self.assertFalse(ContributorEvent.objects.exists())
        self.action("Invited", "without_email")
        view = self.action("Invited", "without_email")
        self.assertIn("must have status None", view.modal_html)
        self.assertEqual(ContributorEvent.objects.count(), 1)

    def test_status_is_rechecked_under_lock(self):
        marketer = Contributor(pk=self.marketer.pk, contributor_type="Marketer")
        marketer.marketer_status = None
        changed = Contributor(pk=self.marketer.pk, contributor_type="Marketer")
        changed.marketer_status = "Confirmed"
        view = self.view({"selected_contributor": str(self.marketer.pk), "delivery": "without_email"})
        with patch.object(view, "_selected_marketers", side_effect=[[marketer], [changed]]):
            view.invite(view.request.POST)
        self.assertFalse(ContributorEvent.objects.exists())
        self.assertIn("must have status None", view.modal_html)

    def test_rejection_requires_confirmation_and_has_no_email_option(self):
        self.record_status("Invited")
        view = self.action("Rejected")
        self.assertIn('value="1">Decline invitation</button>', view.modal_html)
        self.assertNotIn('value="send_email"', view.modal_html)
        self.assertEqual(ContributorEvent.objects.count(), 1)
        self.action("Rejected", "without_email")
        self.assertEqual(self.marketer.contributorevent_set.latest("pk").status, "Rejected")

    @patch("CraftMarket.spreadsheet.CommunicationTemplate.send_email", return_value=1)
    def test_checkbox_submission_invites_without_email_when_unchecked(self, send):
        view = self.action('Invited', confirm_action='1', email_template_id=str(self.templates['Invited'].pk))
        self.assertEqual(self.marketer.contributorevent_set.latest('pk').status, 'Invited')
        send.assert_not_called()
        self.assertNotIn('Status recorded', view.modal_html)

    @patch("CraftMarket.spreadsheet.CommunicationTemplate.send_email", return_value=1)
    def test_checkbox_submission_validates_template_before_inviting(self, send):
        view = self.action('Invited', 'send_email', confirm_action='1')
        self.assertIn('Choose exactly one email template.', view.modal_html)
        self.assertFalse(ContributorEvent.objects.exists())
        send.assert_not_called()
        self.action('Invited', 'send_email', self.templates['Invited'], confirm_action='1')
        self.assertEqual(self.marketer.contributorevent_set.latest('pk').status, 'Invited')
        send.assert_called_once()

    def test_stale_event_and_past_event_do_not_save(self):
        view = self.action("Invited", "without_email", market_event_id=str(self.previous.pk))
        self.assertIn("event has changed", view.modal_html)
        view = self.view({"selected_contributor": str(self.marketer.pk), "delivery": "without_email"}, event=self.previous)
        view.invite(view.request.POST)
        self.assertIn("current or upcoming event", view.modal_html)
        self.assertFalse(ContributorEvent.objects.exists())

    @patch("CraftMarket.spreadsheet.CommunicationTemplate.send_email", side_effect=RuntimeError("delivery failure"))
    def test_email_failure_preserves_status_and_reports_missing_email(self, send):
        with self.assertLogs("CraftMarket.spreadsheet", level="ERROR"):
            view = self.action("Invited", "send_email", self.templates["Invited"],
                               ids=[str(self.marketer.pk), str(self.other.pk)])
        self.assertEqual(ContributorEvent.objects.count(), 2)
        self.assertIn("Email could not be sent", view.modal_html)
        self.assertIn("no email address recorded", view.modal_html)
        send.assert_called_once()

    def test_each_email_gets_fresh_personalised_context(self):
        self.other.email = "birch@example.com"
        contexts = []

        def send(request, context):
            contexts.append(context.copy())
            context.pop("email")
            return 1

        template = Mock(send_email=Mock(side_effect=send))
        self.view()._send_emails([self.marketer, self.other], template)
        self.assertEqual([context["email"] for context in contexts], [["alex@example.com"], ["birch@example.com"]])
        self.assertEqual([context["contact_name"] for context in contexts], ["Alex", "Sirs"])

    def test_write_permission_is_enforced_and_toolbar_hidden(self):
        view = self.view({"toolbar_action": "invite", "selected_contributor": str(self.marketer.pk)})
        view.request.user = Mock(has_perm=Mock(return_value=False))
        self.assertEqual(view.get_extra_toolbar_actions(), ())
        self.assertEqual(view.post(view.request).status_code, 403)
        self.assertFalse(ContributorEvent.objects.exists())
