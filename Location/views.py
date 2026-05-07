from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.http import Http404
from django.shortcuts import redirect, render
from django.template import context
from django.template.response import TemplateResponse
from django.templatetags.static import static
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from fontTools.feaLib import location

from GarageSale.models import CommunicationTemplate
from TeamPageFramework.entry_point import EntryPoint, EntryPointMixin
from user_management.decorators.guest import UserRecognisedMixin
from django.urls import reverse_lazy, reverse

from django.views.generic.edit import CreateView, UpdateView, DeleteView
from django.views.generic import ListView, TemplateView
from .models import Location as LocationModel
from .forms import LocationForm
from django.conf import settings

def view_event_map(request):
    locations = LocationModel.objects.all()
    context = {'GOOGLE_MAP_API': settings.GOOGLE_MAP_SETTINGS.get('API_KEY'),
               'locations' :  LocationModel.objects.filter(event=request.current_event,
                                                        sale_event=True).order_by('creation_timestamp')}
    return TemplateResponse(request, "map_view.html", context  )

class LocationBase(CreateView) :
    model = LocationModel
    form_class = LocationForm
    DEFAULT_TEMPLATE_CATEGORY = "Location"
    DEFAULT_EMAIL_FROM = "website@BranthamGarageSale.org.uk"
    CREATED_TRANSITION = "created"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context |= {'on_behalf': self.request.GET.get('on_behalf', None)}
        context |= {'GOOGLE_MAP_API': settings.GOOGLE_MAP_SETTINGS.get('API_KEY')}
        context |= {"Activity": "Recording new "}
        return context

    def _build_change_description(self, sale_event: bool, ad_board: bool) -> str:
        parts: list[str] = []
        if sale_event:
            parts.append("hosting a sale event")
        if ad_board:
            parts.append("hosting an ad-board")

        description = " and ".join(parts)
        return description[:1].capitalize() + description[1:] if description else ""

    def _send_created_email(self, *, location: "LocationModel") -> None:
        location_settings = settings.APPS_SETTINGS.get("Location", {})
        category = location_settings.get("EmailTemplateCategory", self.DEFAULT_TEMPLATE_CATEGORY)

        template = CommunicationTemplate.get_template_for_category(category, self.CREATED_TRANSITION)
        if not template:
            return

        email_context = {
            "from": location_settings.get("EmailFrom", self.DEFAULT_EMAIL_FROM),
            "email": [self.request.user.email],
            "address": location.full_address(),
            "event_date": location.event.get_event_date_display(),
            "location_description": self._build_change_description(location.sale_event, location.ad_board),
        }
        template.send_email(self.request, context=email_context)

    def form_is_valid(self, form):
        """Add user and event details to the location."""

        on_behalf = self.request.GET.get('on_behalf', [])
        if on_behalf:
            user = get_user_model().objects.get(email=on_behalf)
        else:
            user = self.request.user

        location: LocationModel = form.save(commit=False)
        location.user = user
        location.event = self.request.current_event
        location.save()

        self._send_created_email(location=location)
        return location

class LocationCreateView(LocationBase, UserRecognisedMixin, CreateView):
    """Creation Form for Location"""
    model = LocationModel
    template_name = "location_create_form.html"
    login_url = reverse_lazy("user_management:identify")
    transaction_type = "locations"

    def form_valid(self, form):
        location = self.form_is_valid(form)
        return redirect(reverse("Location:confirm", kwargs={"pk": location.id}))

class LocationConfirmView(UserRecognisedMixin, TemplateView):
    model = LocationModel
    template_name = "location_confirm.html"
    login_url = reverse_lazy("user_management:identify")
    context_object_name = "location"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context |= {'GOOGLE_MAP_API' : settings.GOOGLE_MAP_SETTINGS.get('API_KEY')}
        context |= {self.context_object_name: self.model.objects.get(id=self.kwargs.get('pk'))}
        return context

class LocationView(UserRecognisedMixin, ListView):
    model = LocationModel
    template_name = "location_view.html"
    login_url = reverse_lazy("user_management:identify")

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)

    def get_queryset(self):
        return self.model.objects.filter(event=self.request.current_event,
                                         user=self.request.user).order_by('creation_timestamp')


class LocationEditView(UserRecognisedMixin, UpdateView):
    model = LocationModel
    template_name = "location_create_form.html"
    form_class = LocationForm
    login_url = reverse_lazy("user_management:identify")
    transaction_type = "locations"
    success_url = reverse_lazy('Location:view')

    DEFAULT_TEMPLATE_CATEGORY = "Location"
    DEFAULT_EMAIL_FROM = "website@BranthamGarageSale.org.uk"
    EDITED_TRANSITION = "edited"

    def _get_change_description(self, old, new):
        old_sale, old_add = old
        new_sale, new_add = new
        sale_changed, ad_board_changed = old_sale != new_sale, old_add != new_add
        sale_added, ad_board_added = new_sale and not old_sale, new_add and not old_add
        messages = []
        if sale_changed:
            messages.append(f"is {'now' if sale_added else 'no longer'} hosting a sale event")
        if ad_board_changed:
            messages.append(f"is {'now' if ad_board_added else 'no longer'} hosting an ad-board")
        desc = " and ".join(messages)
        return desc[0].capitalize() + desc[1:]

    def _send_edited_email(self, old, location: "LocationModel") -> None:

        sale, add = old

        location_settings = settings.APPS_SETTINGS.get("Location", {})
        category = location_settings.get("EmailTemplateCategory", self.DEFAULT_TEMPLATE_CATEGORY)
        template = CommunicationTemplate.get_template_for_category(category, self.EDITED_TRANSITION)
        if not template:
            return

        context = { 'from': location_settings.get('EmailFrom', self.DEFAULT_EMAIL_FROM),
                     'email': [self.request.user.email],
                    'address': location.full_address(),
                    'event_date': location.event.get_event_date_display(),
                    'change_description': self._get_change_description((sale, add),
                                                                  (location.sale_event, location.ad_board))}
        template.send_email(self.request, context=context)

    def post(self, request, *args, **kwargs):

        ext_id = self.kwargs.get('ext_id')
        inst = self.model.get_by_ext_id(ext_id)

        sale, add = inst.sale_event, inst.ad_board
        form_result = super().post(request, *args, **kwargs)

        # If this form was valid and is going to the success page, send an email
        if hasattr(form_result, 'url') and form_result.url == self.success_url:
            inst.refresh_from_db()
            self._send_edited_email((sale, add), inst)

        return form_result

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context |= {'GOOGLE_MAP_API' : settings.GOOGLE_MAP_SETTINGS.get('API_KEY')}
        context |= {"Activity" : "Editing "}
        return context

    def get_object(self, queryset=None):
        ext_id = self.kwargs.get('ext_id')
        if not ext_id:
            raise Http404("No location id provided")
        inst = LocationModel.get_by_ext_id(ext_id)
        if not inst:
            raise Http404(f"No location found matching {ext_id}")
        return inst

class LocationDelete(UserRecognisedMixin, DeleteView):
    model = LocationModel
    template_name = "location_delete_form.html"
    login_url = reverse_lazy("user_management:identify")
    transaction_type = "locations"
    success_url = reverse_lazy('Location:view')

    DEFAULT_TEMPLATE_CATEGORY = "Location"
    DEFAULT_EMAIL_FROM = "website@BranthamGarageSale.org.uk"
    DELETION_TRANSITION = "deleted"

    def _send_deleted_email(self, event, address) -> None:
        location_settings = settings.APPS_SETTINGS.get("Location", {})
        category = location_settings.get("EmailTemplateCategory", self.DEFAULT_TEMPLATE_CATEGORY)
        template = CommunicationTemplate.get_template_for_category(category, self.DELETION_TRANSITION)
        if not template:
            return
        context = { 'from': location_settings.get('EmailFrom', self.DEFAULT_EMAIL_FROM),
                     'email': [self.request.user.email],
                    'address': address,
                    'event_date': event.get_event_date_display()}
        template.send_email(self.request, context=context)

    def post(self, request, *args, **kwargs):
        ext_id = self.kwargs.get('ext_id')
        inst = self.model.get_by_ext_id(ext_id)

        event, address = inst.event, inst.full_address()

        form_result = super().post(request, *args, **kwargs)

        # If this form was valid and is going to the success page, send an email
        if hasattr(form_result, 'url') and form_result.url == self.success_url:
            self._send_deleted_email(event, address)

        return form_result

    def get_object(self, queryset=None):
        ext_id = self.kwargs.get('ext_id')
        if not ext_id:
            raise Http404("No location id provided")
        inst = LocationModel.get_by_ext_id(ext_id)
        if not inst:
            raise Http404(f"No location found matching {ext_id}")
        return inst

    def _send_delete_email(self, location: "LocationModel") -> None:

        location_settings = settings.APPS_SETTINGS.get("Location", {})
        category = location_settings.get("EmailTemplateCategory", self.DEFAULT_TEMPLATE_CATEGORY)
        template = CommunicationTemplate.get_template_for_category(category, "deleted")
        if not template:
            return
        location_settings = settings.APPS_SETTINGS.get("Location", {})
        context = { 'from': location_settings.get('EmailFrom', self.DEFAULT_EMAIL_FROM),
                    'email': [self.request.user.email],
                    'address': location.full_address(),
                    'event_date': location.event.get_event_date_display() }
        template.send_email(self.request, context=context)

class AddLocation(EntryPointMixin, LocationBase, PermissionRequiredMixin, View):
    permission_required = "Location.add_location"
    login_url = reverse_lazy("user_management:identify")
    entry_point_permission = "Location.add_location"
    entry_point_url = "Location:AddLocation"
    entry_point_label = "Add Location for user"
    entry_point_icon = static("GarageSale/images/icons/menu/map-marker-svgrepo-com.svg")
    entry_point_nav_page = 'TeamPage'
    entry_point_needs_event = False

    template_name = "teampages/on_behalf.html"

    def get_queryset(self):
        user_model = get_user_model()
        return user_model.objects.filter(is_verified=True, is_staff=False, is_superuser=False)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context |= {'user_list': self.get_queryset() }
        return context

    def form_valid(self, form):
        self.form_is_valid(form)
        return redirect(reverse("TeamPages:Root"))
