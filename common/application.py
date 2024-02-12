#!/usr/bin/env python
# coding=utf-8
"""
    GarageSale.application.py : 

Summary :
    
    
Use Case :
    
    
Testable Statements :
    ...
"""

from django.db import transaction

from django.views import View
from django.contrib.auth.models import User
from django.shortcuts import render, reverse, redirect
from django.core import exceptions
from GarageSale.models import EventData, Location
from django.template.response import TemplateResponse
from django.conf import settings
from django.core.mail import send_mail

from django.utils.html import escape


class ApplicationBase(View):
    model = None
    form = None
    extra_fields = []
    path = ''
    template = ''
    email_template = ''
    subject = ''

    def __init__(self):
        super().__init__()
        self.application_inst = None
        self.location_inst = None
        self.event = None
        self.current_user = None
        self.form_inst = None

    def get(self, request, id=None):
        """render the application form"""
        form_action = reverse(self.path) + '?redirect=' + request.GET.get('redirect', '/getInvolved')

        self.current_user = request.user

        event_id = request.current_event.id
        self.event = EventData.objects.get(id=event_id)

        self._find_location_and_sales()

        if not self.current_user.is_anonymous:
            # Identify data to prefill
            initial = {'email': self.current_user.email,
                       'name': f'{self.current_user.first_name} {self.current_user.last_name}'}
        else:
            initial = None

        # Extract data from the Location if it exists
        if self.location_inst:
            data = {field: getattr(self.location_inst, field) for field in
                    {'house_number', 'street_name', 'town', 'postcode', 'phone', 'mobile'}}
        else:
            data = None

        # Get the extra fields as required.
        if self.application_inst is not None:
            for field in self.extra_fields:
                data[field] = getattr(self.application_inst, field)

        if data is None and initial is None :
            self.form_inst = self.form(anonymous=self.current_user.is_anonymous)
        else:
            self.form_inst = self.form(anonymous=self.current_user.is_anonymous,
                                   data=data, initial=initial)

        return render(request, template_name=self.template,
                      context={'form': self.form_inst,
                               'action': form_action,
                               'delete': True if self.application_inst else False})

    def _find_location_and_sales(self):
        """Find any extant location and billboard instances for this user
            returns None if the instance cannot be found
        """
        # Does this user have a stored location
        if not self.current_user.is_anonymous:
            try:
                self.location_inst = Location.objects.prefetch_related().get(user=self.current_user)
            except exceptions.ObjectDoesNotExist:
                self.location_inst = None
        else:
            self.location_inst = None

        if self.location_inst:
            # Does this user have a billboard instance
            try:
                self.application_inst = self.model.objects.prefetch_related().get(event=self.event,
                                                                                  location__user=self.current_user)
            except exceptions.ObjectDoesNotExist:
                self.application_inst = None
        else:
            self.application_inst = None

    def _save(self):
        new = False
        with transaction.atomic():
            # Create a location instance
            if self.current_user.is_anonymous:
                try:
                    self.current_user = User.objects.get(email=self.form_inst.cleaned_data['email'])
                except User.DoesNotExist:
                    self.current_user = User(
                        username=self.form_inst.cleaned_data['email'],
                        email=self.form_inst.cleaned_data['email'],
                        first_name=self.form_inst.cleaned_data['name'].split(' ')[0],
                        last_name= ' '.join(self.form_inst.cleaned_data['name'].split(' ')[1:]),
                        is_active=False)
                    self.current_user.save()

            if self.location_inst is None:
                self.location_inst = Location(user=self.current_user)

            for field, value in self.form_inst.cleaned_data.items():
                if field not in {'house_number', 'street_name', 'town', 'postcode', 'mobile', 'phone'}:
                    continue
                setattr(self.location_inst, field, value)

            self.location_inst.save()
            if self.application_inst is None:
                new = True
                data = dict()
                for field in self.extra_fields:
                    data[field] = self.form_inst.cleaned_data[field]

                """Create a new SaleLocations Instance"""
                self.application_inst = self.model(location=self.location_inst,
                                                   event=self.event,
                                                   **data)
            else:
                for field in self.extra_fields:
                    setattr(self.application_inst, field, self.form_inst.cleaned_data[field])

            self.application_inst.save()

            if new and self.email_template:
                url = (self.request.build_absolute_uri(
                    location=reverse(self.path, kwargs={"id": self.application_inst.id})))
                base_url = self.request.scheme + r'://' + self.request.get_host()

                html_content = TemplateResponse(self.request, self.email_template,
                                                context={
                                                    'url': url,
                                                    'base_url': base_url}
                                                ).rendered_content
                site_name = settings.SITE_NAME
                if not site_name:
                    site_name = 'Brantham Garage Sale'
                sender = settings.EMAIL_SENDER
                sender = sender if sender else settings.EMAIL_HOST_USER

                send_mail(
                    subject=f'{site_name}: {self.subject}',
                    message=html_content,
                    from_email=f'{sender}',
                    recipient_list=[self.location_inst.user.email],
                    html_message=html_content)

    def post(self, request, id=None):
        """Handle creation editing and deleting"""
        redirect_url = request.GET['redirect']
        form_action = reverse('Billboard:apply') + '?redirect=' + redirect_url
        self.form_inst = self.form(request.POST, anonymous = request.user.is_anonymous)

        self.current_user = request.user

        event_id = request.current_event.id
        self.event = EventData.objects.get(id=event_id)

        # Set self.location_inst and self.billboard_inst
        self._find_location_and_sales()

        # Are there any errors ?
        if not self.form_inst.is_valid():
            return render(request, template_name=self.template,
                          context={'form': self.form_inst,
                                   'action': form_action})

        if request.POST['action'] == 'Save':
            self._save()

            return redirect(reverse('getInvolved'))

        if request.POST['action'] == 'Delete':
            self.application_inst.delete()

            return redirect(reverse('getInvolved'))
