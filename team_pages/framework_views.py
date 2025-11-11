
from abc import abstractmethod

from django.forms import fields
from django.core import exceptions
from django.shortcuts import redirect, reverse
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.template.response import TemplateResponse
from django.views import View
from django.http import HttpResponseServerError

import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

class FrameworkView(LoginRequiredMixin, PermissionRequiredMixin, View):
    """
    An All purpose class for displaying a list and detail/creation forms in one template

    Attributes :
        login_url & redirect_field_name - required by the LoginRequiredMixin
        permission_required - as required by the PermissionRequiredMixin
        template_name : the template to be invoked by the instance to display the data and forms
        form_class : the detail forms to be used - can be none if the detail doesn't need a forms (eg a confirmation button)
        model_class : must be a class of a model which can be instantiated
        success_url :  a static URL to be used if the POST operation succeeds

    Methods :
        get_form( form_instance ) -> Form :
                Can be used to modify the forms if necessary (for example change widgets)

        get_success_url( request, context, **kwargs ) -> url
               If implement this defines the url to be used when the POST succeeds - used in presence to self.success_url

        get_list_query_set( request, **kwargs) -> queryset
               Returns the query set for the sub-list

        get_context_data(request, **kwargs) -> dict
                Must be overridden - returns the context used to drive the relevant template.

        get_object( request, **kwargs) - Model instance
                Must be overridden - will return the instance to be used on the forms (for edit/views)
                Can return None (ie. for create and non-forms actions)

        get_new_instance( request, forms, **kwargs):
                Can be implemented - used when self.get_object returns None
                Can also return None to prevent a save.

        self.do_post_success( self, request, context=None, model_instance=None, form_instance=None, **kwargs)
            can be implemented - can be used for any reason during the POST processing.
            Called once the forms is known to be valid.
            If it returns False then the automatic updating of the instance from the form_data
            if this method updates the instance and intends to return False it must also save the instance
            returning False does not constitute a failure.

            Might need a Pre and post save method in future.
    """
    login_url = '/user/login'           # The URL for login if required
    redirect_field_name = 'redirect'    # The field name the login URL will use to return to
    view_base = ''                      # The friendly name of the View URL
    permission_required = []          # Permission required to access this view - should be defined in the class
    template_name = ''                  # The templated to be used for the view - should be defined in the class
    form_class = None                   # The form to be used for the detail view - can be None
    model_class = None                  # The default model class to be used for the detail view - can be None
    success_url = ''                    # The static success url to be used if the POST succeeds - can be None/empty
    columns:list[str] = []              # The columns to be displayed in the list - should be defined in the class
    toolbar:list[dict[str,str]] = []    # The actions that are displayed in the toolbar - should be defined in the class
    filters:list[dict[str,str]] = {}          # The filters to be displayed in the list - should be defined in the class
    actions:dict[str, dict[str,str]] = {}          # The URLS for valid actions
    can_create = True                   # Whether this view should display the New button
    url_fields = []                     # List of fields that can be replaced within the action url

    def post_save(self, request, instance, form, **kwargs):
        return None

    def get_form(self, form_instance=None):
        if form_instance:
            return form_instance
        else:
            return self.form_class()

    def get_success_url(self, request, context, **kwargs):
        """Returns the URL to be used when the POST succeeds"""
        fragments = [key for key, item in self.request.GET.items() if item == '']
        return reverse(self.view_base) + ('?' + '&'.join(fragments)) if fragments else ''

    def get_list_query_set(self, request, **kwargs):
        """Returns a filtered and ordered queryset for the sub-list"""
        return NotImplemented

    def get_context_data(self, request, **kwargs):
        """Must be extended n to provide extra context data for the templates"""
        return {'columns':self.columns,
                "can_create": self.can_create,
                'toolbar' : self.toolbar,
                "filters": self.filters,
                "actions": self.actions,
                "url_fields":self.url_fields}


    @abstractmethod
    def get_object(self, request, **kwargs):
        """Must be overridden to provide the actual model instance used on this forms"""
        return NotImplemented

    def do_post_success(self, request, context=None, model_instance=None, form_instance=None, **kwargs):
        """Can be overridden to provide an alternative to saving an instance
           If the method returns False then the instance isn't saved.
        """
        return True

    def __init__(self, *args, **kwargs):
        """Validate that some forms of success_url is provided"""
        super().__init__(*args, **kwargs)
        if not hasattr(self, 'success_url') and not hasattr(self, 'get_success_url'):
            raise exceptions.ImproperlyConfigured('Either "success_url" attribute or "get_success_url" '
                                                  'method needs to be implemented') from None

    def get(self, request, **kwargs):
        """Initial get request"""
        context = self.get_context_data(request, **kwargs)
        instance = self.get_object(request, **kwargs)

        if self.form_class:
            if instance:
                context['form'] = self.get_form(self.form_class(instance=instance))
            else:
                context['form'] = self.get_form(None)
        else:
            context['form'] = None

        return TemplateResponse(request, self.template_name, context=context)

    def post(self, request, **kwargs):
        form_data = request.POST

        context = self.get_context_data(request, **kwargs)
        instance = self.get_object(request, **kwargs)

        if self.form_class:
            the_form = self.get_form(self.form_class(request.POST, request.FILES))
        else:
            the_form = None

        # If there is a forms instance then validate the forms (and return if errors)
        if the_form:
            if not the_form.is_valid():
                context['form'] = the_form
                return TemplateResponse(request, self.template_name, context=context)

        # Check for the do_post_success method (if it exists)
        if hasattr(self, 'do_post_success'):
            post_success = self.do_post_success(request, context=context, model_instance=instance, form_instance=the_form, **kwargs)
        else:
            post_success = True

        # A value of post_success of False suppress the automated updating the instance and saving.

        # If the post success was affirmative then update the instance from the forms
        if post_success:
            if instance and the_form:
                for field_name in the_form.fields:
                    image_field= isinstance(the_form.fields[field_name], fields.ImageField)
                    if image_field:
                        clear = f'{field_name}-clear' in request.POST
                        files = field_name in request.FILES
                        if f'{field_name}-clear' in request.POST:
                            setattr(instance, field_name, '')
                        elif field_name in request.FILES:
                            setattr(instance, field_name, the_form.cleaned_data[field_name])
                    else:
                        setattr(instance, field_name, the_form.cleaned_data[field_name])
            elif not instance and the_form:
                if hasattr(self, 'get_new_instance'):
                    instance = self.get_new_instance(request, the_form, **kwargs)
                elif self.model_class:
                    instance = self.model_class(**the_form.cleaned_data)
                else:
                    instance = None

            if instance:
                instance.save()
                self.post_save(request, instance, the_form, **kwargs)

        # Redirect to the correct success url
        if hasattr(self, 'get_success_url'):
            url = self.get_success_url(request, context, **kwargs)
            if url is not NotImplemented:
                return redirect(url)

        if hasattr(self, 'success_url') and self.success_url:
            return redirect(self.success_url)
        else:
            return HttpResponseServerError('No defined success_url for this request !')


