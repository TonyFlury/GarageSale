"""Current contributor spreadsheet entry point and shared template management."""
import logging

from django.shortcuts import redirect
from django.templatetags.static import static
from django.urls import reverse

from CraftMarket.spreadsheet import MarketerSpreadsheetView
from TeamPageFramework.entry_point import EntryPointMixin
from GarageSale.views.template_views import (
    TemplateManagement, TemplatesCreate, TemplatesView, TemplatesEdit, duplicate_template,
)

logger = logging.getLogger('CraftMarket.views')

class MarketEntryPoint(EntryPointMixin, MarketerSpreadsheetView):
    entry_point_url = 'CraftMarket:EntryPoint'
    entry_point_label = 'Craft Market'
    entry_point_nav_page = 'Event participation'
    entry_point_order = 20
    entry_point_permission = 'CraftMarket.view_marketer'
    entry_point_icon = static('GarageSale/images/icons/navigation/market-stand-svgrepo-com.svg')

class MarketTemplates(TemplateManagement):
    template_name = "team_pages/templates.html"
    permission_required =  'CraftMarket.change_marketer'
    category = 'CraftMarket'
    url_base = 'CraftMarket/templates'

    def get_success_url(self, request, context=None, **kwargs):
        return reverse('CraftMarket:templates')

class MarketTemplateCreate(TemplatesCreate):
    category = 'CraftMarket'
    permission_required =  ['CraftMarket.change_marketer', 'GarageSale.change_communicationtemplate']
    sub_category_list = [('Invite','Invite'), ('Confirm','Confirm'), ('Fee Pending','Fee Pending'), ('Cancellation','Cancellation')]
    url_base = 'CraftMarket/templates'
    template_help = """
        <p>The Template system allows consistent messages to be sent to all Craft Marketers.
        Including the ability to personalise emails, and provide key information about the event without needing
        to change the template for every Event, by using Information tags, and attach files to outgoing emails.
                
        <h3>Sub-category Field</h3>
        The Sub-category field identifies when or how this template is used.
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
    permission_required =  ['CraftMarket.change_marketer', 'GarageSale.view_communicationtemplate']
    sub_category_list = MarketTemplateCreate.sub_category_list
    url_base = 'CraftMarket/templates'
    template_help = ""

class MarketTemplateEdit(TemplatesEdit):
    category = 'CraftMarket'
    permission_required =  ['CraftMarket.change_marketer', 'GarageSale.change_communicationtemplate']
    sub_category_list = MarketTemplateCreate.sub_category_list
    url_base = 'CraftMarket/templates'
    template_help = MarketTemplateCreate.template_help

def duplicate(request, template_id):

    new_inst = duplicate_template(template_id)

    return redirect(reverse('CraftMarket:template_edit', kwargs={'template_id': new_inst.id}))

class MarketTemplateDelete(TemplatesView):
    permission_required =  ['CraftMarket.change_marketer', 'GarageSale.delete_communicationtemplate']
    template_name = "team_pages/templates_delete.html"
    url_base = 'CraftMarket/templates'
