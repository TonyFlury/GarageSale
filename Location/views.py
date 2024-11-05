# Create your views here.

from django.views import View
from django.core import exceptions
from django.shortcuts import redirect

from user_management.decorators.guest import UserRecognisedMixin
from user_management.models import UserExtended
from django.urls import reverse, reverse_lazy

from django.template.response import TemplateResponse

from django.views.generic.edit import CreateView
from django.views.generic import ListView
from .models import Location as LocationModel
from .forms import LocationForm


class LocationCreateView(UserRecognisedMixin, CreateView):
    model = LocationModel
    template_name = "location_create_form.html"
    form_class = LocationForm
    login_url = reverse_lazy("user_management:identify")
    transaction_type = "locations"
    success_url = reverse_lazy('Location:view')

    def form_valid(self, form):
        """Add user and event details to the location"""
        inst: LocationModel = form.save(commit=False)
        inst.user = self.request.user
        inst.event = self.request.current_event
        inst.save()
        return redirect(self.success_url)


class LocationView(UserRecognisedMixin, ListView):
    model = LocationModel
    template_name = "location_view.html"
    login_url = reverse_lazy("user_management:identify")

    def setup(self, request, *args, **kwargs):
        print('In LocationView class')
        super().setup(request, *args, **kwargs)

    def get_queryset(self):
        return self.model.objects.filter(event=self.request.current_event, user=self.request.user).order_by('creation_timestamp')