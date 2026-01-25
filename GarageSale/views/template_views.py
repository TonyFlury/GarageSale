import datetime
from copy import copy
from typing import Any
import logging

from django.contrib.admin.widgets import AdminDateWidget
from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import BadRequest
from django.db import models
from django.db.models import Case, When, OuterRef, Exists, QuerySet, Q, Subquery, Value, F
from django.forms import formset_factory, inlineformset_factory
from django.http import HttpRequest
from django.template.response import TemplateResponse
from django.templatetags.static import static
from django.urls import reverse

from GarageSale.forms import TemplateForm, AttachmentForm
from GarageSale.models import CommunicationTemplate, TemplateAttachment
from team_pages.framework_views import FrameworkView


#ToDo Ensure that Template deletion depends on :
# 1. Whether the template is in use - one of the fixed transition types for this category or is mentioned in
#               Attachments for a fixed type.
# 2. if the template is in use, then it can't be the current one - you can delete old templates and
#    future ones so long as one of the named templates still exists.

class TemplateManagement(FrameworkView):
    template_name = "team_pages/templates.html"
    login_url = '/user/login'
    permission_required = 'CraftMarket.can_manage'
    columns = [('warning_as_html_fragment',''),('transition', 'Transition/Type'),('summary','Summary'), ('use_from', 'Use From')]
    model_class = CommunicationTemplate
    form_class = TemplateForm
    category = 'General'
    toolbar = [{'action': 'create', 'label': 'Create'},]

    filters = [ {'id': 'future', 'fragment': '!XFuture','label': 'For Future Use'},
               {'id': 'active', 'fragment': '!XActive', 'label': 'In Use'},
               {'id': 'old', 'fragment': '!XOutOfDate', 'label': 'Out of Date'},
               ]
    template_help = "Help goes here"
    url_fields = ['<int:template_id>']

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        cls = self.__class__
        self.actions = {'create': {'label': 'Create',
                              'icon': static('GarageSale/images/icons/create-note-alt-svgrepo-com.svg')},
                   'edit': {'label': 'Edit Details',
                            'icon': static('GarageSale/images/icons/pencil-edit-office-2-svgrepo-com.svg')},
                   'view': {'label': 'View Details',
                            'icon': static('GarageSale/images/icons/execute-inspect-svgrepo-com.svg')},
                   'duplicate': {'label': 'Duplicate Template',
                            'icon': static('GarageSale/images/icons/duplicate-svgrepo-com.svg')},
                   'delete': {'label': 'Delete',
                            'icon': static('GarageSale/images/icons/backspace-svgrepo-com.svg')},}

    def get_cancel_url(self, request, **kwargs):
        """Get a separate cancellation url for forms - can be overriden"""
        return self.get_success_url(request, **kwargs)

    def get_success_url(self, request, context=None, **kwargs):
        return reverse('CraftMarket:templates')

    def get_object(self, request, **kwargs) ->  Any | None :
        return None

    def _get_template_warning(self, qs:QuerySet, request: HttpRequest, **kwargs) -> QuerySet:
        """Generate a simple warning if the attachments are invalid
            Either :
                A named attachment doesn't exist,
                or
                A named attachment does exist but doesn't have a current use_from date.
        """
        def _get_fragment(text):
            return f'<span><image id="warning" href="{{% static \"GarageSale/images/icons/warning-svgrepo-com.svg\" %}}" /><label for="warning">{text}</label></span>'

        existing_names = (CommunicationTemplate.objects.filter(category=self.category).values('use_from').
                                                                                        annotate(name=F('transition')))

        named_missing = Exists(TemplateAttachment.objects.
                              filter(template=OuterRef('pk'), upload=False).
                              exclude(template_name__in = Subquery(existing_names.values('name'))))

        out_of_date = Exists(TemplateAttachment.objects.
                              filter(template=OuterRef('pk'), upload=False).
                              exclude(template_name__in = Subquery(existing_names.
                                                          filter(use_from__lte=OuterRef("template__use_from")).
                                                          values('name'))))

        warnings = Case( When(condition=named_missing & out_of_date,
                                then=Value('Missing and out of date Attachments')),
                        When(condition=out_of_date & (~named_missing),
                             then=Value('Attachment Out of Date')),
                         When(condition= (~out_of_date) & named_missing,
                              then=Value('Named attachments missing')),
                         When(condition= (~named_missing) & (~out_of_date), then=Value(None)),
                         default=Value(""),
                         output_field=models.CharField() )

        qs = qs.annotate(warning_text=warnings)
        return qs


    def _get_actions(self, qs: QuerySet, request: HttpRequest) :
        """Add in the relevant actions column based on the template dates"""
        older = CommunicationTemplate.objects.filter(category = self.category, transition=OuterRef('transition'), use_from__lt = OuterRef('use_from'))

        for row in qs:
            older = CommunicationTemplate.objects.filter(category = self.category, transition=row.transition, use_from__lt = row.use_from)
            if older.exists():
                row.allowed_actions = 'view,edit,duplicate,delete'.split(',')
            else:
                row.allowed_actions = 'view,edit,duplicate'.split(',')
            yield row

    def _add_filters(self, qs: QuerySet, request: HttpRequest) -> QuerySet:
        """Add filters to the base queryset based on the requested filters"""
        newer = CommunicationTemplate.objects.filter(category = self.category, use_from__lte=datetime.date.today(), transition=OuterRef('transition'), use_from__gt = OuterRef('use_from'))

        qi = Q()
        if 'XActive' in request.GET:
            qi &= ~Q(use_from__lte = datetime.date.today())

        if 'XFuture' in request.GET:
            qi &= ~Q(use_from__gt = datetime.date.today())

        if 'XOutOfDate' in request.GET:
            qi &= ~(Q(use_from__lt = datetime.date.today()) & Q(Exists(newer)))

        qs = qs.filter(qi)
        return qs

    def get_list_query_set(self, request: HttpRequest, **kwargs):
        qs =  CommunicationTemplate.objects.filter(category=self.category)
        qs = self._add_filters(qs, request)
        qs = self._get_template_warning(qs, request)
        qs = qs.order_by('transition', '-use_from')
        yield from self._get_actions(qs, request)

    def get_context_data(self, request, **kwargs):
        context = super().get_context_data(request, **kwargs)
        context |= {'data_type': 'Communication Template',
                    'sub_list_data': self.get_list_query_set(request, **kwargs),
                    'base_url' : self.view_base,
                    'success_url': self.get_success_url(request, **kwargs),
                    'cancel_url': self.get_cancel_url(request, **kwargs),
                    'template_help':self.template_help}
        return context

class TemplatesCreate(TemplateManagement):
    template_name = "team_pages/templates_create.html"
    form_class = TemplateForm
    transition_list = []

    def post(self, request, **kwargs):
        if request.POST.get('Add', None) == 'Add +':
            cp = request.POST.copy()

            count = sum(1 for i in request.POST if i.startswith('attachments') and
                                    (i.endswith('attached_file'))) + 1
            cp['attachments-TOTAL_FORMS'] = str(int(cp['attachments-TOTAL_FORMS']) + 1)

            fs = formset_factory(AttachmentForm, extra=0, can_delete=True, can_delete_extra=True)(cp, prefix='attachments')
            fs._errors = {}
            for form in fs:
                form._errors = {}

            normal_form = self.get_form(self.form_class(request.POST))

            normal_form._errors = {}
            context = self.get_context_data(request, **kwargs)
            context |= {'form': normal_form, 'attachments':fs }

            return TemplateResponse(request, self.template_name, context=context)
        else:
            return super().post( request, **kwargs)

    def post_save(self, request, instance, form, **kwargs):
        """Implemented so that any attachments are saved within"""
        for i in range(int(request.POST.get('attachments-TOTAL_FORMS', '0'))):
            inst_id = request.POST.get(f'attachments-{i}-id', None)
            upload = request.FILES.get(f'attachments-{i}-upload', False)
            template_name = request.POST.get(f'attachments-{i}-template_name', None) if not upload else None
            attached_file = request.FILES.get(f'attachments-{i}-attached_file', None) if upload else None

            if inst_id:
                inst = TemplateAttachment.objects.get(id=inst_id)
                inst.upload = upload
                inst.template_name = template_name
                inst.attached_file = attached_file
                inst.save()
            else:
                inst = TemplateAttachment.objects.create(template=instance,
                                                         upload=upload,template_name=template_name,attached_file=attached_file)

    def get_attachments_form(self, request, instance, **kwargs):
        template_id = kwargs.get('template_id', None)
        factory = formset_factory(AttachmentForm, can_delete=True)
        data = { "attachments-TOTAL_FORMS": "0", "attachments-INITIAL_FORMS": "0" }
        initial = []
        formset = factory( data=data, initial=initial, prefix='attachments')
        return formset

    def get_context_data(self, request, **kwargs):
        context = super().get_context_data(request, **kwargs)
        instance = self.get_object(request, **kwargs)
        context |= {'action': 'create',
                    'attachments': self.get_attachments_form(request, instance, **kwargs)}
        return context

    def get_form(self, form_instance=None):
        # Set the category field and limit the transitions to those for the current category

        if form_instance is None:
            form_instance = self.form_class(initial={'category':self.category, 'transition':[self.transition_list[0][0],'']})

        form_instance.fields['category'].initial = self.category
        form_instance.fields['category'].widget.attrs['readonly'] = True
        # form_instance.fields['transition'].choices = self.transition_list + [('Other','Other')]
        form_instance.fields['transition'].widget.widgets[0].choices=self.transition_list + [('Other','Other')]
        form_instance.fields['transition'].widget.widgets[0].initial=self.transition_list[0][0]

        form_instance.fields['use_from'].widget = AdminDateWidget(attrs={'type': 'date'})
        form_instance.fields['use_from'].initial = datetime.date.today()
        form_instance.fields['use_from'].widget.default = datetime.date.today()
        form_instance.fields['use_from'].widget.input_formats = ['%d %m %Y']

        return form_instance

class TemplatesView(TemplateManagement):
    template_name = "team_pages/templates_view.html"
    form_class = TemplateForm
    transition_list = []
    template_help = ''

    def get_object(self, request, **kwargs) ->  Any | None :
        return CommunicationTemplate.objects.get(id=kwargs.get('template_id', None))

    def get_attachments_form(self, request, instance, **kwargs):
        if instance:
            template_id = instance.id
        else:
            template_id = kwargs.get('template_id', None)
        #factory = formset_factory(AttachmentForm, extra=1, can_delete=True)
        attachments = TemplateAttachment.objects.filter(template_id=template_id)
        return attachments

    def get_context_data(self, request, **kwargs):
        context = super().get_context_data(request, **kwargs)
        instance = self.get_object(request, **kwargs)
        context |= {'action': 'create',
                    'attachments': self.get_attachments_form(request, instance=instance, **kwargs),
                    'base_url' : reverse('CraftMarket:templates')}
        return context

    def get_form(self, form_instance=None):
        # Set the category field and limit the transitions to those for the current category

        if form_instance is None:
            form_instance = self.form_class(initial={'category':self.category, 'transition':[self.transition_list[0][0],'']})

        form_instance.fields['category'].initial = self.category
        form_instance.fields['category'].widget.attrs['readonly'] = True
        form_instance.fields['transition'].widget.widgets[0].choices=self.transition_list + [('Other','Other')]
        form_instance.fields['transition'].widget.widgets[0].initial=self.transition_list[0][0]

        return form_instance

class TemplatesEdit(TemplatesView):
    template_name = "team_pages/templates_edit.html"
    form_class = TemplateForm
    transition_list = []
    template_help = ''

    def get_context_data(self, request, **kwargs):
        context = super().get_context_data(request, **kwargs)
        instance = self.get_object(request, **kwargs)
        context |= {'action': 'edit',
                    'base_url': reverse('CraftMarket:templates'),
                    'cancel_url' : self.get_cancel_url(request, **kwargs),
                    'attachments': self.get_attachments_form(request, instance, **kwargs)}
        return context

    def get_attachments_form(self, request, instance, **kwargs):

        if not instance:
            inst_id = kwargs.get('template_id', None)
            try:
                instance = CommunicationTemplate.objects.get(id)
            except CommunicationTemplate.DoesNotExist:
                logging.error(f'Cannot find template with id {inst_id}')
                raise BadRequest(f'Cannot find template with id {inst_id}')

        factory = inlineformset_factory(CommunicationTemplate,
                                        TemplateAttachment,
                                        fields=('id', 'upload','template_name','attached_file'),
                                        extra=0, can_delete=True)

        if request.method == 'POST':
            formset = factory( request.POST, request.FILES, instance=instance,
                                prefix='attachments')
        else:
            formset = factory(instance=instance, prefix='attachments',)

        return formset

    def post(self, request, **kwargs):
        if request.POST.get('Add', None) == 'Add +':
            cp = request.POST.copy()
            count = cp.get('attachments-TOTAL_FORMS', '0')
            cp['attachments-TOTAL_FORMS'] = str(int(cp['attachments-TOTAL_FORMS']) + 1)

            fs = inlineformset_factory(parent_model=CommunicationTemplate,
                                       model=TemplateAttachment,
                                       fields=('id', 'upload','template_name','attached_file'),
                                       extra=1, can_delete=True)(cp, prefix='attachments')

            # Prevent errors on the Add
            fs._errors = {}
            for form in fs:
                form._errors = {}

            normal_form = self.get_form(self.form_class(request.POST))

            normal_form._errors = {}
            context = self.get_context_data(request, **kwargs)
            context |= {'form': normal_form, 'attachments': fs}

            return TemplateResponse(request, self.template_name, context=context)
        else:
            return super().post(request, **kwargs)

    def post_save(self, request, instance, form, **kwargs):
        """Implemented so that any attachments are saved within"""
        print( f'post_save called {request.POST.get('attachments-TOTAL_FORMS', '0')}' )
        for i in range(int(request.POST.get('attachments-TOTAL_FORMS', '0'))):
            print(f'i = {i}, {request.POST.get(f"attachments-{i}-template_name")}, {request.POST.get(f"attachments-{i}-DELETE")}')

        formset = self.get_attachments_form(request, instance, **kwargs)

        if formset.is_valid():
            formset.save()
        else:
            print(formset.errors)

def duplicate_template(inst_id):

    try:
        instance = CommunicationTemplate.objects.get(id=inst_id)
    except CommunicationTemplate.DoesNotExist:
        logging.error(f'Cannot find template with id {inst_id}')
        raise BadRequest(f'Cannot find template with id {inst_id}')

    new_inst = copy(instance)
    new_inst.id = new_inst.pk = None
    new_inst.use_from = datetime.date.today()
    new_inst.summary = f'{new_inst.summary} (Duplicate)'
    new_inst.save()

    for attachment in instance.attachments.all():
        new_attachment = copy(attachment)
        new_attachment.id = new_attachment.pk = None
        new_attachment.template = new_inst
        new_attachment.save()

    return new_inst