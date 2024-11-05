import datetime
import csv

from django.forms import fields
from django.core import exceptions
from django.core.exceptions import BadRequest
from django.db.models import Q
from django.shortcuts import redirect, reverse
from django.urls import reverse_lazy
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.template.response import TemplateResponse
from django.views import View
from django.http import HttpResponseServerError, HttpResponse
from django.contrib.admin.widgets import AdminDateWidget

from News.models import NewsArticle
from News.views import publish_news
from Sponsors.models import Sponsor
from GarageSale.models import MOTD, EventData
from .forms import NewsForm, MotdForm, EventForm, SponsorForm
from Sponsors.views import social_media_items
from abc import abstractmethod

def PublishNews(request, news_id):
    publish_news(request, news_id)
    fragments = [key for key, item in request.GET.items() if item == '']
    print(reverse('TeamPagesNews'))
    return redirect(reverse('TeamPagesNews') + (('?' + '&'.join(fragments)) if fragments else ''))


def custom_news_query_set(param_dict):
    unpublished = 'unpublished' in param_dict
    xpublished = 'Xpublished' in param_dict
    xfront_page = 'XFrontPage' in param_dict
    xnot_front_page = 'XNotFrontPage' in param_dict
    expired = 'expired' in param_dict

    # base includes Everything
    if unpublished:
        qp = Q(published=False)
    else:
        qp = Q(published=True)

    if not xpublished:
        qp |= Q(published=True)
    else:
        qp |= Q(published=False)

    if xfront_page:
        qf = Q(front_page=False)
    else:
        qf = Q(front_page=True)

    if xnot_front_page:
        qf |= Q(front_page=True)
    else:
        qf |= Q(front_page=False)

    if not expired:
        q = (qp & qf) & Q(expire_by__isnull=True) | Q(expire_by__gte=datetime.date.today())
    else:
        q = qp & qf

    return NewsArticle.chainable.filter(q).order_by('-published', 'publish_by', '-front_page')


class CombinedView(LoginRequiredMixin, PermissionRequiredMixin, View):
    """
    An All purpose class for displaying a list and detail/creation form in one template

    Attributes :
        login_url & redirect_field_name - required by the LoginRequiredMixin
        permission_required - as required by the PermissionRequiredMixin
        template_name : the template to be invoked by the instance to display the data and form
        form_class : the detail form to be used - can be none if the detail doesn't need a form (eg a confirmation button)
        model_class : must be a class of a model which can be instantiated
        success_url :  a static URL to be used if the POST operation succeeds

    Methods :
        get_form( form_instance ) -> Form :
                Can be used to modify the form if necessary (for example change widgets)

        get_success_url( request, context, **kwargs ) -> url
               If implement this defines the url to be used when the POST succeeds - used in presence to self.success_url

        get_list_query_set( request, **kwargs) -> queryset
               Returns the query set for the sub-list

        get_context_data(request, **kwargs) -> dict
                Must be overridden - returns the context used to drive the relevant template.

        get_object( request, **kwargs) - Model instance
                Must be overridden - will return the instance to be used on the form (for edit/views)
                Can return None (ie. for create and non-form actions)

        get_new_instance( request, form, **kwargs):
                Can be implemented - used when self.get_object returns None
                Can also return None to prevent a save.

        self.do_post_success( self, request, context=None, model_instance=None, form_instance=None, **kwargs)
            can be implemented - can be used for any reason during the POST processing.
            Called once the form is known to be valid.
            If it returns False then the automatic updating of the instance from the form_data
            if this method updates the instance and intends to return False it must also save the instance
            returning False does not constitute a failure.

            Might need a Pre and post save method in future.
    """
    login_url = '/user/login'
    redirect_field_name = 'redirect'
    permission_required = None
    template_name = ''
    form_class = None
    model_class = None
    success_url = ''

    def get_form(self, form_instance=None):
        return form_instance

    def get_success_url(self, request, context, **kwargs):
        """Returns the URL to be used when the POST succeeds"""
        return NotImplemented

    def get_list_query_set(self, request, **kwargs):
        """Returns a filtered and ordered queryset for the sub-list"""
        return NotImplemented

    @abstractmethod
    def get_context_data(self, request, **kwargs):
        """Must be overridden to provide extra context data for the templates"""
        return {}

    @abstractmethod
    def get_object(self, request, **kwargs):
        """Must be overridden to provide the actual model instance used on this form"""
        return NotImplemented

    def do_post_success(self, request, context=None, model_instance=None, form_instance=None, **kwargs):
        """Can be overridden to provide an alternative to saving an instance
           If the method returns False then the instance isn't saved.
        """
        return True

    def __init__(self, *args, **kwargs):
        """Validate that some form of success_url is provided"""
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
                context['form'] = self.get_form(self.form_class())
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

        # If there is a form instance then validate the form (and return if errors)
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

        # If the post success was affirmative then update the instance from the form
        if post_success:
            if instance and the_form:
                for field_name in the_form.fields:
                    image_field= isinstance(the_form.fields[field_name], fields.ImageField)
                    if image_field:
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

        # Redirect to the correct success url
        if hasattr(self, 'get_success_url'):
            url = self.get_success_url(request, context, **kwargs)
            if url is not NotImplemented:
                return redirect(url)

        if hasattr(self, 'success_url') and self.success_url:
            return redirect(self.success_url)
        else:
            return HttpResponseServerError('No defined success_url for this request !')


class NewsRoot(CombinedView):
    permission_required = ["News.can_manage_news"]
    template_name = 'news/tp_manage_news.html'
    form_class = NewsForm
    model_class = NewsArticle

    def get_success_url(self, request, context=None, **kwargs):
        fragments = [key for key, item in self.request.GET.items() if item == '']
        return reverse('TeamPagesNews') + ('?' + '&'.join(fragments)) if fragments else ''

    def get_object(self, request, **kwargs):
        return None

    def get_list_query_set(self, request, **kwargs):
        return custom_news_query_set(request.GET)

    def get_context_data(self, request, **kwargs):
        """Provide the context data for the templates"""

        context = {'data_type': 'news', 'news_id': kwargs.get('news_id', None),
                   'sub_list_data': self.get_list_query_set(request, **kwargs),
                   'patterns': [
                       {'action': 'create', 'regex': 'news/create/'},
                       {'action': 'edit', 'regex': 'news/<int:news_id>/edit/'},
                       {'action': 'view', 'regex': 'news/<int:news_id>/view/'},
                       {'action': 'publish', 'regex': 'news/<int:news_id>/publish/'},
                       {'action': 'delete', 'regex': 'news/<int:news_id>/delete/'},
                       {'action': 'cancel', 'regex': 'news/'}]
                   }
        return context


class NewsEdit(NewsRoot):
    permission_required = ["News.can_edit_news"]
    form_class = NewsForm
    template_name = 'news/tp_edit_news.html'

    def get_context_data(self, request, **request_kwargs):
        context = super().get_context_data(request, **request_kwargs)
        context['action'] = 'edit'
        return context

    def get_object(self, request, **kwargs):
        this_object = None
        try:
            this_object = NewsArticle.objects.get(id=kwargs.get('news_id', None))
        except NewsArticle.DoesNotExist:
            raise BadRequest(f'Invalid News Id {kwargs.get("news_id", None)}')
        return this_object


class NewsView(NewsEdit):
    """get_object is the same in both cases"""
    permission_required = ["News.can_view_news"]
    template_name = 'news/tp_view_news.html'

    def get_context_data(self, request, **request_kwargs):
        context = super().get_context_data(request, **request_kwargs)
        context['action'] = 'view'
        return context


class NewsCreate(NewsRoot):
    permission_required = ["News.can_create_news"]
    template_name = 'news/tp_create_news.html'

    def get_context_data(self, request, **request_kwargs):
        context = super().get_context_data(request, **request_kwargs)
        context['action'] = 'create'
        return context

    def get_object(self, request, **kwargs):
        return None


class NewsDelete(NewsView):
    template_name = 'news/tp_delete_news.html'
    permission_required = ["News.can_delete_news"]
    form_class = None

    def get_context_data(self, request, **kwargs):
        context = super().get_context_data(request,**kwargs)
        obj:NewsArticle = self.get_object( request, **kwargs)
        return context | {'action':'delete', 'headline':obj.headline}

    def do_post_success(self, request, context=None, model_instance:NewsArticle=None, form_instance=None, **kwargs):
        model_instance.delete()
        return False

class MotDBase(CombinedView):
    login_url = '/user/login'
    redirect_field_name = 'redirect'
    form_class = MotdForm
    model_class = MOTD
    success_url = reverse_lazy('TeamPagesRoot')

    def get_context_data(self, request, **kwargs):
        return {}

    def get_success_url(self, request, context=None, **kwargs):
        """Returns the URL to be used when the POST succeeds"""
        return NotImplemented


class MotDView(MotDBase):
    permission_required = ["GarageSale.can_view_motd"]
    template_name = 'motd/tp_view_motd.html'

    def get_context_data(self, request, **kwargs):
        context = super().get_context_data(request, **kwargs)
        context |= {'data_type': 'motd', 'action': 'view', 'motd_id': kwargs.get('motd_id', None)}
        return context

    def get_object(self, request, **kwargs):
        if 'motd_id' in kwargs:
            try:
                inst = MOTD.objects.get(id=kwargs['motd_id'])
            except MOTD.DoesNotExist:
                raise BadRequest(f'MOTD with an unknown id {kwargs["motd_id"]} cannot be viewed')
        else:
            raise BadRequest(f'MOTD view without an Id ')

        return inst


class MotDEdit(MotDView):
    permission_required = ["GarageSale.can_edit_motd"]
    template_name = 'motd/tp_edit_motd.html'

    def get_context_data(self, request, **kwargs):
        context = super().get_context_data(request, **kwargs)
        context |= {'data_type': 'motd', 'action': 'edit', 'motd_id': kwargs.get('motd_id', None)}
        return context


class MotDCreate(MotDBase):
    permission_required = ["GarageSale.can_create_motd"]
    template_name = 'motd/tp_create_motd.html'

    def get_context_data(self, request, **kwargs):
        context = super().get_context_data(request, **kwargs)
        context |= {'data_type': 'motd', 'action': 'create', 'motd_id': None}
        return context

    def get_object(self, request, **kwargs):
        return None


def delete_motd(request, motd_id=None):
    try:
        instance: MOTD = MOTD.objects.get(id=motd_id)
    except MOTD.DoesNotExist:
        raise BadRequest(f'Invalid id for MOTD: {motd_id}')

    instance.delete()
    return redirect(reverse('TeamPagesRoot'))


class EventBase(CombinedView):
    permission_required = ["GarageSale.can_view_event"]
    template_name = 'motd/tp_view_event.html'
    form_class = EventForm
    model = EventData

    def get_form(self, form=None):
        """Add the Admin Date Widget to all date fields - by name for now"""
        form = super().get_form(form)
        for field in ['event_date',
                      'open_billboard_bookings', 'close_billboard_bookings', 'open_sales_bookings',
                      'close_sales_bookings',
                      'use_from']:
            form.fields[field].widget = AdminDateWidget(attrs={'type': 'date'})
            form.fields[field].default = datetime.date.today() + datetime.timedelta(1)
            form.fields[field].input_formts = ['%d %m %Y']
        return form

    def get_context_data(self, request, **kwargs):
        context = super().get_context_data(request, **kwargs)
        context = context if context != NotImplemented else {}
        context |= {'data_type': 'event', 'action': 'view', 'event_id': kwargs.get('event_id', None)}
        return context

    def get_object(self, request, **kwargs):
        try:
            instance = EventData.objects.get(id=kwargs.get('event_id', None))
        except EventData.DoesNotExist:
            raise BadRequest('Invalid event_id {event_id} for viewing')
        return instance


class EventView(EventBase):
    permission_required = ["GarageSale.can_view_event"]
    template_name = 'event/tp_view_event.html'

    def get_context_data(self, request, **kwargs):
        context = super().get_context_data(request, **kwargs)
        context['action'] = 'view'
        return context


class EventEdit(EventView):
    permission_required = ["GarageSale.can_edit_event"]
    template_name = 'event/tp_edit_event.html'
    success_url = reverse_lazy( 'TeamPagesEvent')

    def get_context_data(self, request, **kwargs):
        context = super().get_context_data(request, **kwargs)
        context['action'] = 'edit'
        return context


class EventCreate(EventBase):
    permission_required = ["GarageSale.can_create_event"]
    template_name = 'event/tp_create_event.html'
    success_url = reverse_lazy( 'TeamPagesEvent')

    def get_context_data(self, request, **kwargs):
        context = super().get_context_data(request, **kwargs)
        context['action'] = 'create'
        return context

    def get_object(self, request, **kwargs):
        return None


def event_use(request, event_id):
    """Simple invocation of a template - option to add more complexity if needed"""
    return TemplateResponse(request, 'event/tp_use_event.html', context={'event_id': event_id, 'data_type': 'sponsor'})


class TeamPage(LoginRequiredMixin, View):
    login_url = "/user/login"
    redirect_field_name = "/team_page"

    def get(self, request, event_id=None):
        context = {'event_id': event_id}
        return TemplateResponse(request, 'team_page.html', context=context)


class SponsorsRoot(CombinedView):
    login_url = "/user/login"
    redirect_field_name = "/team_page"
    permission_required = ["Sponsors.can_view_sponsor"]
    model_class = Sponsor
    form_class = SponsorForm
    template_name = 'sponsors/tp_event_sponsor.html'

    def get_success_url(self, request, context=None, **kwargs):
        event_id = context.get('event_id')
        return reverse('TeamPagesSponsor', kwargs={'event_id':event_id})

    def get_context_data(self, request, **kwargs):
        context = super().get_context_data(request, **kwargs)

        event_id = kwargs.get('event_id', None)
        sponsor_id = kwargs.get('sponsor_id', None)

        if sponsor_id:
            sponsor_obj = self.get_object(request, **kwargs)
            event_id = sponsor_obj.event.id
        else:
            sponsor_obj = None

        context |= {'sub_list_data': Sponsor.objects.filter(event__id=event_id).
                    values("id", "company_name", "confirmed").order_by("creation_date").all(),
                    'data_type': 'sponsor',
                    'event_id': event_id,
                    'sponsor_id': sponsor_obj.id if sponsor_obj else None,
                    'action': None,
                    'socials': social_media_items(),
                    'patterns': [
                        {'action': 'create', 'regex': 'sponsor/<int:event_id>/create/'},
                        {'action': 'edit', 'regex': 'sponsor/<int:sponsor_id>/edit/'},
                        {'action': 'view', 'regex': 'sponsor/<int:sponsor_id>/view/'},
                        {'action': 'confirm', 'regex': 'sponsor/<int:sponsor_id>/confirm/'},
                        {'action': 'delete', 'regex': 'sponsor/<int:sponsor_id>/delete/'},
                        {'action': 'cancel', 'regex': 'sponsor/<int:event_id>/'}]
                    }
        return context

    def get_object(self, request, **kwargs):
        return None


class SponsorCreate(SponsorsRoot):
    template_name = 'sponsors/tp_create_sponsor.html'
    permission_required = ["Sponsors.can_create_sponsor"]

    def get_context_data(self, request, **kwargs):
        return super().get_context_data(request, **kwargs) | {'create':'action'}

    def get_object(self, request, **kwargs):
        return None

    def get_new_instance(self, request, form, **kwargs):
        try:
            event = EventData.objects.get(id = kwargs.get('event_id'))
        except EventData.DoesNotExist:
            raise BadRequest(f'Cannot create a sponsorship record without a valid event {kwargs.get("event_id")}')

        inst = self.model_class(event=event, **form.cleaned_data)
        return inst


class SponsorView(SponsorsRoot):
    template_name = 'sponsors/tp_view_sponsor.html'
    permission_required = ["Sponsors.can_view_sponsor"]

    def get_context_data(self, request, **kwargs):
        context = super().get_context_data(request, **kwargs)
        obj = self.get_object(request, **kwargs)

        context |= {'action': 'view',
                    'event_id': obj.event.id,
                    'sponsor_id': kwargs.get('sponsor_id', None)}
        return context

    def get_object(self, request, **kwargs):
        sponsor_id = kwargs.get('sponsor_id', None)
        try:
            return Sponsor.objects.get(id=sponsor_id)
        except Sponsor.DoesNotExist:
            raise BadRequest(f'Unknown/invalid sponsor_id {sponsor_id}')


class SponsorEdit(SponsorView):
    template_name = 'sponsors/tp_edit_sponsor.html'
    permission_required = ["Sponsors.can_edit_sponsor"]

    def get_context_data(self, request, **kwargs):
        return super().get_context_data(request,**kwargs) | {'action':'edit'}


class SponsorConfirm(SponsorView):
    template_name = 'sponsors/tp_confirm_sponsor.html'
    permission_required = ["Sponsors.can_confirm_sponsor"]
    form_class = None

    def get_context_data(self, request, **kwargs):
        context = super().get_context_data(request,**kwargs)
        obj:Sponsor = self.get_object( request, **kwargs)
        return context| {'action':'confirm', 'company_name':obj.company_name}

    def do_post_success(self, request, context=None, model_instance:Sponsor=None, form_instance=None, **kwargs):
        model_instance.confirmed = True
        model_instance.save()
        return False


class SponsorDelete(SponsorView):
    template_name = 'sponsors/tp_delete_sponsor.html'
    permission_required = ["Sponsors.can_delete_sponsor"]
    form_class = None

    def get_context_data(self, request, **kwargs):
        context = super().get_context_data(request,**kwargs)
        obj:Sponsor = self.get_object( request, **kwargs)
        return context| {'action':'delete', 'company_name':obj.company_name}

    def do_post_success(self, request, context=None, model_instance:Sponsor=None, form_instance=None, **kwargs):
        model_instance.delete()
        return False


def ad_board_csv(request, event_id):
    event = EventData.objects.get(id = event_id)
    qs = BillboardLocations.objects.filter(event=event)

    response = HttpResponse(content_type='text/csv',
                            headers={"Content-Disposition": 'attachment; filename="advert_boards.csv"'},)

    writer=csv.writer(response)
    writer.writerow(['Name', 'Address', 'Postcode', 'Phone', 'Mobile'])
    for entry in qs:
        writer.writerow([f'{entry.name()}',
                         f'{entry.full_address()}',
                         f'{entry.location.postcode}',
                         f'{entry.location.phone}',
                         f'{entry.location.mobile}'])
    return response
