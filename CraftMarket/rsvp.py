"""Invitation links and RSVP handling for contributor-based market traders."""
from types import SimpleNamespace

from django.conf import settings
from django.core import signing
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.template import Context, Template
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils import timezone
from django.views import View

from Contributors.models import Contributor, ContributorEvent
from CraftMarket.forms import RSVPForm
from GarageSale.models import CommunicationTemplate

SALT = 'CraftMarket.contributor-rsvp'


def invitation_url(request, marketer, event):
    latest = ContributorEvent.objects.filter(contributor=marketer, event=event).order_by('-timestamp', '-pk').first()
    if latest is None or latest.status != 'Invited':
        return ''
    token = signing.dumps({'invitation': latest.pk, 'email': marketer.email}, salt=SALT)
    return request.build_absolute_uri(reverse('CraftMarket:ContributorRSVP', kwargs={'token': token}))


class ContributorRSVP(View):
    template_name = 'portal/craft_market_RSVP.html'

    def render(self, request, **context):
        return TemplateResponse(request, self.template_name, context)

    def dispatch(self, request, *args, **kwargs):
        try:
            data = signing.loads(kwargs['token'], salt=SALT)
            self.invitation = ContributorEvent.objects.select_related('contributor', 'event').get(
                pk=data['invitation'], status='Invited', contributor__contributor_type='Marketer',
                contributor__email=data['email'],
            )
        except (signing.BadSignature, ContributorEvent.DoesNotExist, KeyError, TypeError):
            return self.render(request, error='Invalid invitation link. Please check your email or contact the Craft Market team.')
        latest = ContributorEvent.objects.filter(
            contributor=self.invitation.contributor, event=self.invitation.event,
        ).order_by('-timestamp', '-pk').first()
        if latest.pk != self.invitation.pk or self.invitation.event.event_date < timezone.localdate():
            return self.render(request, error='This invitation is no longer active. Please contact the Craft Market team.')
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, **kwargs):
        return self.render(request, form_section='portal_login', form=RSVPForm())

    def post(self, request, **kwargs):
        invitation = self.invitation
        trader = invitation.contributor
        session_key = f'craft_market_rsvp_{invitation.pk}'
        if request.POST.get('form_section') == 'portal_login':
            form = RSVPForm(request.POST)
            if not form.is_valid():
                return self.render(request, form_section='portal_login', form=form)
            if form.cleaned_data['email'].casefold() != trader.email.casefold():
                form.add_error('email', 'Please enter the email address that received this invitation.')
                return self.render(request, form_section='portal_login', form=form)
            request.session[session_key] = True
        elif request.POST.get('form_section') == 'accept_reject' and request.session.get(session_key):
            accept = 'RSVP_Yes' in request.POST
            reject = 'RSVP_No' in request.POST
            if accept != reject:
                with transaction.atomic():
                    # Serialize with the spreadsheet's status changes and reject repeated responses.
                    get_object_or_404(Contributor.objects.select_for_update(), pk=trader.pk)
                    latest = ContributorEvent.objects.filter(contributor=trader, event=invitation.event).order_by('-timestamp', '-pk').first()
                    if latest.pk != invitation.pk:
                        return self.render(request, error='This invitation has already been answered or changed.')
                    ContributorEvent.objects.create(contributor=trader, event=invitation.event,
                                                    status='Confirmed' if accept else 'Rejected')
                request.session.pop(session_key, None)
                if accept:
                    # Use the same personalised email context and delivery handling as the spreadsheet.
                    from CraftMarket.spreadsheet import MarketerSpreadsheetView
                    view = MarketerSpreadsheetView()
                    view.setup(request, event_id=invitation.event_id)
                    templates = view._available_templates('Confirmed')
                    if templates:
                        view._send_emails([trader], templates[0])
                return self.render(request, form_section='accept' if accept else 'reject',
                                   marketer=SimpleNamespace(trading_name=trader.contributor_name, id=trader.pk))
        else:
            return self.render(request, form_section='portal_login', form=RSVPForm())

        category = settings.APPS_SETTINGS['CraftMarket']['EmailTemplateCategory']
        terms = CommunicationTemplate.current_active.filter(category=category, sub_category='TermsAndConditions').first()
        context = CommunicationTemplate.default_context(request, {'current_event': invitation.event})
        context.update(trading_name=trader.contributor_name, contact_name=trader.contact_name,
                       url=invitation_url(request, trader, invitation.event))
        tos = Template(terms.html_content).render(Context(context)) if terms else ''
        return self.render(request, form_section='accept_reject', tos=tos,
                           marketer=SimpleNamespace(trading_name=trader.contributor_name, id=trader.pk))
