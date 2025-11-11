import logging

from django.core.exceptions import BadRequest
from django.db import models
from django.http import HttpRequest
from django.shortcuts import redirect
from django.template import Template
from django.template.response import TemplateResponse
from django.templatetags.static import static
from django.urls import reverse, reverse_lazy
from django.utils.encoding import force_str
from django.contrib.postgres.fields import ArrayField
from django.views import View

from django.db.models import Q, Case, When, Value, QuerySet, Max

import CraftMarket.forms
from GarageSale.models import EventData, CommunicationTemplate
from CraftMarket.models import Marketer, MarketerState
from CraftMarket.forms import MarketerForm
from GarageSale.views.template_views import TemplateManagement, TemplatesCreate, TemplatesView, TemplatesEdit, \
    duplicate_template

from team_pages.framework_views import FrameworkView


logger = logging.getLogger('CraftMarket.views')

# Create your views here.

def craft_market_list(request):
    return None

# TODO - prevent the need to repeat the full url for each action.
# TODO - framework should be able to construct the URL based on the action name, the relevant object
# TODO - and the base URL

class TeamPages(FrameworkView):
    login_url = '/user/login'
    permission_required  = 'GarageSale.is_trustee'
    template_name = "team_pages/craft_market.html"
    view_base = "CraftMarket:TeamPages"
    columns = [('trading_name', 'Trading<br>Name'), ('state_name', 'Current<br>Status')]
    can_create = True
    model_class = Marketer
    form_class = MarketerForm
    toolbar = [{'action': 'create', 'label': 'Create', 'regex': '/CraftMarket/<int:event_id>/create/', 'icon': ''},
               {'action': 'templates', 'label': 'Templates', 'regex': '/CraftMarket/templates/', 'icon': ''},
               ]
    filters = [{'id': 'marketer_invited', 'fragment': '!XInvited', 'pair': True, 'label': 'Invited'},
               {'id': 'marketer_responded', 'fragment': '!XResponded', 'pair': True, 'label': 'Responded'},
               {'id': 'marketer_rejected', 'fragment': '!XRejected', 'label': 'Rejected'},
               ]
    actions = {'create': {'label': 'Create', 'regex': '/CraftMarket/<int:event_id>/create/',
                          'icon': static('/GarageSale/images/icons/create-note-alt-svgrepo-com.svg')},
               'templates': {'label': 'Templates', 'regex': '/CraftMarket/templates/',
                             'icon': static('/GarageSale/images/icons/visit-templates-svgrepo-com.svg')},
               'edit': {'label': 'Edit Details', 'regex': '/CraftMarket/<int:marketer_id>/edit/',
                        'icon': static('GarageSale/images/icons/pencil-edit-office-2-svgrepo-com.svg')},
               'view': {'label': 'View Details', 'regex': '/CraftMarket/<int:marketer_id>/view/',
                        'icon': static('GarageSale/images/icons/execute-inspect-svgrepo-com.svg')},
               'cancel': {'label': 'Cancel', 'regex': '/CraftMarket/<int:event_id>/',
                          'icon': static('GarageSale/images/icons/cancel-svgrepo-com.svg')},
               'invite': {'label': 'Invite to Event', 'regex': '',
                          'icon': static('GarageSale/images/icons/invite-svgrepo-com.svg')},
               'confirm': {'label': 'Confirm Attendance', 'regex': '',
                           'icon': static('GarageSale/images/icons/thumb-up-svgrepo-com.svg')},
               'reject': {'label': 'Reject Invite', 'regex': '',
                          'icon': static('GarageSale/images/icons/thumb-down-svgrepo-com.svg')}, }
    url_fields = ['<int:event_id>', '<int:marketer_id>']

    def get_success_url(self, request, context=None, **kwargs):
        event_id = context.get('event_id')
        return reverse('CraftMarket:TeamPages', kwargs={'event_id': event_id})

    def get_object(self, request, **kwargs) -> Marketer | None:
        """There is no relevant object for the base class"""
        return None

    @staticmethod
    def __add_actions(qs: QuerySet, request: HttpRequest) -> QuerySet:
        """Add in the relevant actions column based on the user permissions"""

        current_user = request.user

        actions_per_row: dict[str, list[str]] = {}
        for state, label in MarketerState.choices:
            actions_per_row[state] = ['view']

            if current_user.has_perm('CraftMarket.can_manage'):
                match label:
                    case 'New':
                        actions_per_row[state] += ['edit','invite']
                    case 'Invited':
                        actions_per_row[state] += ['confirm','reject']
                    case '_' | 'Confirmed' | 'Rejected' :
                        pass

        the_case = Case(*[When(state=key, then=action_list) for key, action_list in actions_per_row.items()],
                        output_field=ArrayField(models.CharField()))

        new_qs = qs.annotate(allowed_actions=the_case)
        return new_qs

    @staticmethod
    def __add_filters(qs: QuerySet, request: HttpRequest) -> QuerySet:
        """Add filters to the base queryset based on the requested filters"""
        if 'XInvited' in request.GET:
            qi = Q(state__in=[MarketerState.New ])
        else:
            qi = Q()

        if 'NotXInvited' in request.GET:
            qi &= ~Q(state__in=[MarketerState.New])

        if 'XResponded' in request.GET:
            qresp = ~Q(state__in=[MarketerState.Confirmed, MarketerState.Rejected])
        else:
            qresp = Q()

        if 'NotXResponded' in request.GET:
            qresp = ~Q(state__in=[MarketerState.Confirmed, MarketerState.Rejected])

        if 'XRejected' in request.GET:
            qreject = ~Q(state=MarketerState.Rejected)
        else:
            qreject = Q()

        q_full = qi & qresp & qreject

        return qs.filter(q_full)

    def get_list_query_set(self, request: HttpRequest, **kwargs):
        """Get the query set for this request based on the relevant filters"""

        event_id = kwargs.get('event_id', None)
        marketer_id = kwargs.get('marketer_id', None)

        if event_id is None:
            marketer: Marketer | None = self.get_object(request, **kwargs)
            if marketer is None:
                logging.error(f'Unable to identify the event for {request.path}')
                raise BadRequest(f'Unable to identify the event for {request.path}')

            event_id = marketer.event.id

        if event_id is None:
            logging.error(f'Unable to identify the event for {request.path}')
            raise BadRequest(f'Unable to identify the event for {request.path}')

        qs = Marketer.objects.filter(event__id=event_id).annotate(
            state_name=Case(
                *[
                    When(state=key, then=Value(force_str(val))) for key, val in MarketerState.choices
                ],
                default=Value("New!"),
                output_field=models.CharField()
            )
        )

        qs = self.__add_actions(qs, request)
        qs = self.__add_filters(qs, request)

        return qs

    def get_context_data(self, request, **kwargs):
        context = super().get_context_data(request, **kwargs)
        context |= {'data_type': 'Marketer',
                    'event_id': kwargs.get('event_id', None),
                    'marketer_id': kwargs.get('marketer_id', None),
                    'sub_list_data': self.get_list_query_set(request, **kwargs)}
        # Remove the 'templates button' if the user does not have the required permissions
        if not request.user.has_perm('CraftMarket.can_manage'):
            context['toolbar'] = [i for i in context['toolbar'] if i['action'] != 'templates']
        return context


class TeamPagesCreate(TeamPages):
    permission_required  = 'GarageSale.is_trustee'
    template_name = "team_pages/craft_market_create.html"
    form_class = MarketerForm
    model_class = Marketer

    def get_context_data(self, request, **kwargs):
        context = super().get_context_data(request, **kwargs)
        context |= {'action': 'create'}
        return context

    def get_new_instance(self, request, form, **kwargs):
        try:
            event = EventData.objects.get(id=kwargs.get('event_id'))
        except EventData.DoesNotExist:
            raise BadRequest(
                f'Cannot create a record for a Craft Marketer without a valid event {kwargs.get("event_id")}')

        inst = self.model_class.objects.create(event=event, **form.cleaned_data)
        return inst

class TeamPagesView(TeamPages):
    template_name = "team_pages/craft_market_view.html"
    permission_required = ['GarageSale.is_trustee']

    def get_context_data(self, request, **kwargs):
        context = super().get_context_data(request, **kwargs)
        inst_obj = self.get_object(request, **kwargs)
        context |= {'action': 'view', 'event_id':inst_obj.event.id, 'marketer_id': inst_obj.id}
        context |= {'history': inst_obj.history.values('state').annotate(latest_date=Max('timestamp')).order_by('-latest_date')}
        return context

    def get_object(self, request, **kwargs) -> Marketer | None:
        if kwargs.get('marketer', None) is None:
            raise BadRequest(
                f'Cannot view a record for a Craft Marketer without a valid marketer {kwargs.get("marketer")}')
        return Marketer.objects.get(id=kwargs.get('marketer'))

class TeamPagesEdit(TeamPagesView):
    template_name = "team_pages/craft_market_edit.html"
    permission_required = ['CraftMarket.can_manage']

    def get(self, request, **kwargs):
        return super().get(request, **kwargs)

class TeamPagesGenericStateChange(TeamPages):
    template_name = "team_pages/craft_market_invite.html"
    view_base = "CraftMarket:TeamPages"
    new_state: MarketerState

    def get_object(self, request, **kwargs) -> Marketer | None:
        if kwargs.get('marketer', None) is None:
            raise BadRequest(
                f'Cannot view a record for a Craft Marketer without a valid marketer {kwargs.get("marketer")}')
        return Marketer.objects.get(id=kwargs.get('marketer'))

    def get_context_data(self, request, **kwargs):
        context = super().get_context_data( request, **kwargs)
        inst = self.get_object(request, **kwargs)
        event_id = inst.event.id
        context |= {'action': self.new_state.label,
                    'event_id': event_id,
                    'marketer_id': inst.id,
                    'instance': self.get_object(request, **kwargs),
                    'email':not 'no_email' in request.GET}
        return context

    # Overriding all the get function as there is no form here - confirmation is by pop-up
    def get(self, request, **kwargs):
        send_email:bool = not 'no_email' in request.GET
        marketer_id = kwargs.get('marketer', None)
        try:
            marketer = Marketer.objects.get(id=marketer_id)
        except Marketer.DoesNotExist:
            logging.error(f'Invalid Marketer value {marketer_id} during invite request')
            raise BadRequest(f'Invalid Marketer value {marketer_id}')

        logger.debug(f'Updating Marketer state to {self.new_state} for {marketer.email} - {send_email=}')
        marketer.update_state(self.new_state, request=request, send_email=send_email)

        return redirect(reverse(self.view_base, kwargs={'event_id': marketer.event.id}))

class TeamPagesInvite(TeamPagesGenericStateChange):
    template_name = "team_pages/craft_market_invite.html"
    view_base = "CraftMarket:TeamPages"
    new_state =  MarketerState.Invited

class TeamPagesConfirm(TeamPagesGenericStateChange):
    template_name = "team_pages/craft_market_confirm.html"
    view_base = "CraftMarket:TeamPages"
    new_state =  MarketerState.Confirmed

class TeamPagesReject(TeamPagesGenericStateChange):
    template_name = "team_pages/craft_market_reject.html"
    view_base = "CraftMarket:TeamPages"
    new_state = MarketerState.Rejected

class MarketerRSVP(View):
    template_name = "portal/craft_market_RSVP.html"

    def _portal_login(self, request, **kwargs):
        marketer_code = kwargs.get('marketer_code', None)
        email = request.POST.get('email', None)

        if not Marketer.Checksum.validate_checksum(marketer_code):
            logging.error(f'Invalid Marketer Code checksum- provided {marketer_code} during RSVP request')
            form = CraftMarket.forms.RSVPForm()
            form.add_error('email', 'Invalid Request to Market Portal - please check your emails and try again')
            return TemplateResponse(request=request, template=self.template_name,
                                    context={'form_section':'portal_login', 'form' : form, 'valid': False})
        else:
            try:
                marketer = Marketer.objects.get(email=email, code=marketer_code)
            except Marketer.DoesNotExist:
                logging.error(f'Invalid Marketer Code {marketer_code} for {email} during RSVP request')
                return TemplateResponse(request=request, template=self.template_name,
                                        context={'form_section':'portal_login',
                                                 'form' : CraftMarket.forms.RSVPForm(),
                                                 'valid': False,
                                                 'error': 'Invalid Request to Market Portal - please check your emails and try again'})

        try:
            tos_template = CommunicationTemplate.current_active.filter(category='CraftMarket', transition='TermsAndConditions').latest('use_from')
            tos_html = tos_template.html_content
        except CommunicationTemplate.DoesNotExist:
            logging.error(f'Could not find a valid Terms and Conditions template for {marketer}')
            tos_html = '{% lorem 5 p %}'

        tos = Template(tos_html).render(context=marketer.common_context(request=request))

        return TemplateResponse(request=request, template=self.template_name,
                                context={'form_section':'accept_reject',
                                          'tos': tos
                                        ,'marketer':marketer})


    def _accept_reject_form(self, request, **kwargs):

        logger.debug(f'in _accept_reject_form with {request.POST=}')
        accept, reject = request.POST.get('RSVP_Yes', False), request.POST.get('RSVP_No', False)
        marketer_id = request.POST.get('marketer_id', None)

        form_section = 'accept' if accept else 'reject' if reject else None
        new_state = MarketerState.Confirmed if accept else MarketerState.Rejected if reject else None

        try:
            inst = Marketer.objects.get(id=marketer_id)
        except Marketer.DoesNotExist:
            logging.error(f'Could not find Marketer with id {marketer_id} during RSVP request')
            raise BadRequest(
                'We are unable to process your request at this time - please try again later, or contact the organiser.')

        if form_section is None:
            logging.error(f'Invalid RSVP selection {accept=}, {reject=} for {inst} during RSVP request')
            return TemplateResponse(request=request, template=self.template_name,
                                    context={'form_section':'accept_reject','marketer_id':marketer_id,
                                             'marketer':inst,
                                             'error': 'We did not understand your response - please try again'} )
        else:

            inst.update_state(new_state, request=request, send_email=True)
            inst.refresh_from_db()
            logger.debug(f'Updated Marketer state to {inst.state} for {inst.email}')
            return TemplateResponse(request=request, template=self.template_name,
                             context={'form_section': form_section,
                                      'marketer': inst})

    def get(self, request:HttpRequest, **kwargs):

        marketer_code = kwargs.get('marketer_code', None)

        if not Marketer.Checksum.validate_checksum(marketer_code):
            logging.error(f'Invalid Marketer Code checksum- provided {marketer_code} during RSVP request')
            return TemplateResponse(request=request, template=self.template_name,
                                    context={'form_section':'portal_login',
                                             'error': 'Invalid Request to Market Portal - please check your emails and try again'})
        else:
            return TemplateResponse(request=request, template=self.template_name,
                        context={'form_section': 'portal_login',
                                 'form':CraftMarket.forms.RSVPForm()})

    def post(self, request, **kwargs):

        form_section = request.POST.get('form_section', None)
        logger.debug(f'in post with {form_section=} {request.POST.get('marketer_id', None)=} ')

        match form_section:
            case 'portal_login':
                return self._portal_login(request, **kwargs)
            case 'accept_reject':
                return self._accept_reject_form(request, **kwargs)
            case _:
                raise BadRequest(f'Invalid form_section: {form_section}')

class MarketTemplates(TemplateManagement):
    template_name = "team_pages/templates.html"
    permission_required =  'CraftMarket.can_manage'
    category = 'CraftMarket'
    view_base = reverse_lazy('CraftMarket:templates')

    def get_success_url(self, request, context=None, **kwargs):
        return reverse('CraftMarket:templates')

class MarketTemplateCreate(TemplatesCreate):
    category = 'CraftMarket'
    permission_required =  'CraftMarket.can_manage'
    transition_list = [('Invite','Invite'), ('Confirm','Confirm')]
    view_base = reverse_lazy('CraftMarket:templates')
    template_help = """
        <p>The Template system allows consistent messages to be sent to all Craft Marketers.
        Including the ability to personalise emails, and provide key information about the event without needing
        to change the template for every Event, by using Information tags, and attach files to outgoing emails.
                
        <h3>Transition/Type Field</h3>
        The Transition/Type field identifies when or how this template is used.
        <ul>
        <li> Invite - Is used when a Craft Marketer is invited to participate in the event
        <li> Confirm - Is used when a Craft Marketer has confirmed they will participate in the event
        <li> Other - Allows you to enter your own custom Type - typically used for attachements.
        </ul>

        <h3>Information tags</h3>
        The following tags can be used in the subject and content areas so that emails are personalised, and
        specific to a given event (this reduces the need to update the template for every event).
        
        <h4>Event Information</h4>
        <ul>
        <li> {{event_date}} - A nicely formated date for the event
        <li> {{supporting}} - A list of the names of the charities being supported by this event
        </ul>
        <h4>Craft Marketer Information</h4>
        <ul>
        <li> {{trading_name}} - The trading name of the Craft Marketer
        <li> {{contact_name}} - The given contact name of the Craft Marketer
        <li> {{email}} - The email address of the Craft Marketer
        <li> {{url}} - The unique portal URL for this Craft Marketer - used in Invite emails.
        </ul>
        To make use of these tags, make sure you include the {{ }} around the name as above.
        
        <h3>Attachments</h3>
        The Template system can attach one or more files to outgoing emails. Attachments can either be : 
        <ul>
        <li> An uploaded fixed file of any file type (eg an image or a PDF file) or
        <li> A named template from the CraftMarket Category - in this case the Template is converted 
        to a PDF and attached to the email,
        </ul>
    """

    def get_success_url(self, request, context=None, **kwargs):
        return reverse('CraftMarket:templates')


class MarketTemplateView(TemplatesView):
    category = 'CraftMarket'
    permission_required =  'CraftMarket.can_manage'
    transition_list = [('Invite','Invite'), ('Confirm','Confirm')]
    view_base = reverse_lazy('CraftMarket:templates')
    template_help = ""

class MarketTemplateEdit(TemplatesEdit):
    category = 'CraftMarket'
    permission_required =  'CraftMarket.can_manage'
    transition_list = [('Invite','Invite'), ('Confirm','Confirm')]
    view_base = reverse_lazy('CraftMarket:templates')
    template_help = MarketTemplateCreate.template_name

def duplicate(request, template_id):

    new_inst = duplicate_template(template_id)

    return redirect(reverse('CraftMarket:template_edit', kwargs={'template_id': new_inst.id}))

class MarketTemplateDelete(TeamPages):
    permission_required =  'CraftMarket.can_manage'
    template_name = "team_pages/templates_delete.html"
    view_base = reverse_lazy('CraftMarket:templates')