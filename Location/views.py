from django.http import Http404
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.views import View

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

class LocationCreateView(UserRecognisedMixin, CreateView):
    """Creation Form for Location"""
    model = LocationModel
    template_name = "location_create_form.html"
    form_class = LocationForm
    login_url = reverse_lazy("user_management:identify")
    transaction_type = "locations"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context |= {'GOOGLE_MAP_API' : settings.GOOGLE_MAP_SETTINGS.get('API_KEY')}
        context |= {"Activity" : "Recording new "}
        return context

    def form_valid(self, form):
        """Add user and event details to the location"""
        inst: LocationModel = form.save(commit=False)
        inst.user = self.request.user
        inst.event = self.request.current_event
        inst.save()

        #To DO - send confirmation email.
        return redirect(reverse('Location:confirm', kwargs={'pk':inst.id,}))

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

#To Do - send email if the data has changed !

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

    def get_object(self, queryset=None):
        ext_id = self.kwargs.get('ext_id')
        if not ext_id:
            raise Http404("No location id provided")
        inst = LocationModel.get_by_ext_id(ext_id)
        if not inst:
            raise Http404(f"No location found matching {ext_id}")
        return inst

# ToDo - send confirmation of deletion ????