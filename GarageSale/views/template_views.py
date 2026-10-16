import datetime
from copy import copy
from urllib.parse import urlencode
from typing import Any
import logging

from django.contrib.admin.widgets import AdminDateWidget
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import BadRequest
from django.db import models, transaction
from django.db.models import Case, When, OuterRef, Exists, QuerySet, Q, Subquery, Value, F
from django.forms import formset_factory, inlineformset_factory
from django.http import HttpRequest, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.templatetags.static import static
from django.urls import reverse
from django.views.generic import CreateView, DetailView, TemplateView, UpdateView
from django.utils import timezone
from django.views import View

from GarageSale.forms import TemplateForm, AttachmentForm, CommunicationTemplateWebsiteForm, CommunicationTemplateAttachmentForm
from GarageSale.models import CommunicationTemplate, TemplateAttachment
from GarageSale.access_policy import template_categories, require_template
from team_pages.framework_views import FrameworkView
from TeamPageFramework.entry_point import EntryPointMixin


class CommunicationTemplateCategories(EntryPointMixin, LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    """List communication template summaries for a selected category."""

    template_name = "team_pages/communication_template_categories.html"
    permission_required = "GarageSale.view_communicationtemplate"
    entry_point_url = "TeamPages:CommunicationTemplates"
    entry_point_label = "Communication Templates"
    entry_point_icon = static("GarageSale/images/icons/folder-templates-svgrepo-com.svg")
    entry_point_permission = permission_required
    entry_point_needs_event = False
    entry_point_nav_page = "TeamPagesData"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # List every template by summary, including old and future versions.
        permitted = template_categories(self.request.user)
        queryset = CommunicationTemplate.objects.order_by("category", "summary", "-use_from", "pk")
        if permitted is not None:
            queryset = queryset.filter(category__in=permitted)
        rows = queryset.values_list(
            "category", "summary", "use_from", "pk", "sub_category",
        )
        categories = {}
        for category, summary, use_from, pk, sub_category in rows:
            categories.setdefault(category, []).append({"pk": pk, "summary": summary or "", "use_from": use_from, "sub_category": sub_category or ""})
        context["template_categories"] = [
            {"name": category} for category in sorted(categories)
        ]

        # Show summaries only for a category chosen from the available list.
        selected_category = self.request.GET.get("category")
        context["selected_category"] = selected_category if selected_category in categories else None
        context["templates"] = categories.get(selected_category, [])

        # Check only the displayed category and attach warning text to its rows.
        warnings = CommunicationTemplate.attachment_warnings_for([
            CommunicationTemplate(pk=row["pk"], category=selected_category,
                                  sub_category=row["sub_category"], use_from=row["use_from"])
            for row in context["templates"]
        ])
        for row in context["templates"]:
            row["attachment_warning"] = warnings.get(row["pk"], "")
        return context


class CommunicationTemplateFormView(LoginRequiredMixin, PermissionRequiredMixin):
    model = CommunicationTemplate
    form_class = CommunicationTemplateWebsiteForm
    template_name = "team_pages/communication_template_form.html"

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        categories = template_categories(self.request.user, "manage")
        if categories is not None:
            form.fields["category"].widget = __import__("django.forms", fromlist=["Select"]).Select(
                choices=[(category, category) for category in sorted(categories)])
        return form

    def get_attachment_formset(self, instance=None):
        factory = inlineformset_factory(
            CommunicationTemplate, TemplateAttachment, form=CommunicationTemplateAttachmentForm,
            fields=("upload", "template_name", "attached_file"), extra=0, can_delete=True,
        )
        kwargs = {"instance": instance or self.object, "prefix": "attachments"}

        # Bind files and attachment values on submission so validation can be shown in place.
        if self.request.method == "POST":
            kwargs.update(data=self.request.POST, files=self.request.FILES)
        attachments = factory(**kwargs)

        # Every explicitly added row needs a name or file, unless marked for deletion.
        if self.request.method == "POST":
            for attachment_form in attachments.forms:
                attachment_form.empty_permitted = False
        return attachments

    def form_valid(self, form):
        require_template(self.request.user, form.cleaned_data["category"], "change" if self.object else "add")
        attachments = self.get_attachment_formset(instance=form.instance)

        # Keep the form open without saving anything if an attachment is invalid.
        if not attachments.is_valid():
            return self.render_to_response(self.get_context_data(form=form, attachments=attachments))

        # Save the template and its attachment entries as one database transaction.
        with transaction.atomic():
            self.object = form.save()
            attachments.instance = self.object
            attachments.save()
        return HttpResponseRedirect(self.get_success_url())

    def get_success_url(self):

        # Return to the category containing the saved template.
        return reverse("TeamPages:CommunicationTemplates") + "?" + urlencode({"category": self.object.category})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Preserve the submitted formset and its errors when rerendering the form.
        if "attachments" not in context:
            context["attachments"] = self.get_attachment_formset()
        category = self.object.category if self.object else self.request.GET.get("category", "")
        context["cancel_url"] = reverse("TeamPages:CommunicationTemplates")
        if category:
            context["cancel_url"] += "?" + urlencode({"category": category})
        return context


class CommunicationTemplateCreate(CommunicationTemplateFormView, CreateView):
    permission_required = "GarageSale.add_communicationtemplate"

    def get_initial(self):
        initial = super().get_initial()
        initial.update(category=self.request.GET.get("category", ""), use_from=timezone.localdate())
        return initial


class CommunicationTemplateEdit(CommunicationTemplateFormView, UpdateView):
    permission_required = "GarageSale.change_communicationtemplate"


class CommunicationTemplateDuplicate(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = ("GarageSale.add_communicationtemplate", "GarageSale.change_communicationtemplate")
    http_method_names = ["post", "options"]

    def post(self, request, pk):

        # Copy the saved template and attachment entries together before opening the new version.
        with transaction.atomic():
            source = get_object_or_404(CommunicationTemplate.objects.select_for_update(), pk=pk)
            duplicate = duplicate_template(source.pk, preserve_summary=True)
        return HttpResponseRedirect(reverse("TeamPages:CommunicationTemplateEdit", args=[duplicate.pk]))


class CommunicationTemplateDelete(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = CommunicationTemplate
    permission_required = "GarageSale.delete_communicationtemplate"
    template_name = "team_pages/communication_template_delete.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Explain blocked deletion on the confirmation page.
        if "deletion_errors" not in context:
            context["deletion_errors"] = self.object.deletion_errors()
        context["cancel_url"] = reverse("TeamPages:CommunicationTemplates") + "?" + urlencode({"category": self.object.category})
        return context

    def post(self, request, *args, **kwargs):
        template = self.get_object()

        # Lock the category's versions so concurrent deletions cannot remove each other's replacements.
        with transaction.atomic():
            category_templates = CommunicationTemplate.objects.select_for_update().filter(
                category=template.category,
            ).order_by("pk")
            list(category_templates)
            self.object = get_object_or_404(category_templates, pk=template.pk)
            errors = self.object.deletion_errors()

            # Recheck the rules at submission time; never delete from a GET request.
            if errors:
                return self.render_to_response(self.get_context_data(deletion_errors=errors), status=409)
            redirect_url = self.get_context_data(deletion_errors=[])['cancel_url']
            self.object.delete()
        return HttpResponseRedirect(redirect_url)


#ToDo Ensure that Template deletion depends on :
# 1. Whether the template is in use - one of the fixed sub_category types for this category or is mentioned in
#               Attachments for a fixed type.
# 2. if the template is in use, then it can't be the current one - you can delete old templates and
#    future ones so long as one of the named templates still exists.

class TemplateManagement(FrameworkView):
    template_name = "team_pages/templates.html"
    login_url = '/user/login'
    permission_required = 'CraftMarket.view_marketer'
    columns = [('warning_as_html_fragment',''),('sub_category', 'Sub-category'),('summary','Summary'), ('use_from', 'Use From')]
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
                                                                                        annotate(name=F('sub_category')))

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
        older = CommunicationTemplate.objects.filter(category = self.category, sub_category=OuterRef('sub_category'), use_from__lt = OuterRef('use_from'))

        for row in qs:
            older = CommunicationTemplate.objects.filter(category = self.category, sub_category=row.sub_category, use_from__lt = row.use_from)
            if older.exists():
                row.allowed_actions = 'view,edit,duplicate,delete'.split(',')
            else:
                row.allowed_actions = 'view,edit,duplicate'.split(',')
            yield row

    def _add_filters(self, qs: QuerySet, request: HttpRequest) -> QuerySet:
        """Add filters to the base queryset based on the requested filters"""
        newer = CommunicationTemplate.objects.filter(category = self.category, use_from__lte=datetime.date.today(), sub_category=OuterRef('sub_category'), use_from__gt = OuterRef('use_from'))

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
        qs = qs.order_by('sub_category', '-use_from')
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
    sub_category_list = []

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
            form_instance = self.form_class(initial={'category':self.category, 'sub_category':[self.sub_category_list[0][0],'']})

        form_instance.fields['category'].initial = self.category
        form_instance.fields['category'].widget.attrs['readonly'] = True

        # form_instance.fields['sub_category'].choices = self.sub_category_list + [('Other','Other')]
        form_instance.fields['sub_category'].widget.widgets[0].choices=self.sub_category_list + [('Other','Other')]
        form_instance.fields['sub_category'].widget.widgets[0].initial=self.sub_category_list[0][0]

        form_instance.fields['use_from'].widget = AdminDateWidget(attrs={'type': 'date'})
        form_instance.fields['use_from'].initial = datetime.date.today()
        form_instance.fields['use_from'].widget.default = datetime.date.today()
        form_instance.fields['use_from'].widget.input_formats = ['%d %m %Y']

        return form_instance

class TemplatesView(TemplateManagement):
    template_name = "team_pages/templates_view.html"
    form_class = TemplateForm
    sub_category_list = []
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
            form_instance = self.form_class(initial={'category':self.category, 'sub_category':[self.sub_category_list[0][0],'']})

        form_instance.fields['category'].initial = self.category
        form_instance.fields['category'].widget.attrs['readonly'] = True
        form_instance.fields['sub_category'].widget.widgets[0].choices=self.sub_category_list + [('Other','Other')]
        form_instance.fields['sub_category'].widget.widgets[0].initial=self.sub_category_list[0][0]

        return form_instance

class TemplatesEdit(TemplatesView):
    template_name = "team_pages/templates_edit.html"
    form_class = TemplateForm
    sub_category_list = []
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
        formset = self.get_attachments_form(request, instance, **kwargs)

        if formset.is_valid():
            formset.save()

def duplicate_template(inst_id, *, preserve_summary=False):

    try:
        instance = CommunicationTemplate.objects.get(id=inst_id)
    except CommunicationTemplate.DoesNotExist:
        logging.error(f'Cannot find template with id {inst_id}')
        raise BadRequest(f'Cannot find template with id {inst_id}')

    new_inst = copy(instance)
    new_inst.id = new_inst.pk = None
    new_inst.use_from = timezone.localdate()

    # Website duplication creates another version with the same summary.
    if not preserve_summary:
        new_inst.summary = f'{new_inst.summary} (Duplicate)'
    new_inst.save()

    for attachment in instance.attachments.all():
        new_attachment = copy(attachment)
        new_attachment.id = new_attachment.pk = None
        new_attachment.template = new_inst
        new_attachment.save()

    return new_inst
