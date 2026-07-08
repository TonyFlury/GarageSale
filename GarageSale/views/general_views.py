#!/usr/bin/env python
# coding=utf-8
"""
    GarageSale.general_views.py :

Summary :
    
    
Use Case :
    
    
Testable Statements :
    ...
"""
from django.template.response import TemplateResponse
from django.http import HttpRequest
from django.urls import reverse_lazy
from django.shortcuts import redirect
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from News.models import NewsArticle
from django.views.generic import CreateView, ListView, DetailView
from django.templatetags.static import static
from TeamPageFramework.entry_point import EntryPointMixin
from ..models import Nomination

# from .forms import TestForm
from ..forms import NominationCreate
from ..models import Nomination

def home(incoming_request: HttpRequest) -> TemplateResponse:
    qs = NewsArticle.FrontPageOrder.all()
    t = TemplateResponse(incoming_request, template="home.html", context={'articles': qs})
    return t

#def testing(request, case=0):
#    if request.method == "POST":
#        form = TestForm(request.POST)
#    else:
#        match case:
#            case 0:
#                form = TestForm()
#            case 2:
#                form = TestForm({'location':'{ "lat": 51.961053274564065, "lng": 1.0698445125573741 }'})

#    return TemplateResponse(request, "test.html", context={'form': form})


class NominationCreateView(CreateView):
    model = Nomination
    form_class = NominationCreate
    template_name = 'team_pages/nominations/nomination_form.html'
    success_url = reverse_lazy('NominationSuccess')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user if self.request.user.is_authenticated else None
        return kwargs


class NominationsList(EntryPointMixin, LoginRequiredMixin, PermissionRequiredMixin, ListView):
    login_url = reverse_lazy('user_management:login')
    redirect_field_name = 'next'
    permission_required = 'GarageSale.is_trustee'
    entry_point_url = 'NominationsList'
    entry_point_label = 'Funding Nominations'
    entry_point_icon = static('GarageSale/images/icons/navigation/loving-charity-svgrepo-com.svg')
    entry_point_permission = 'GarageSale.is_trustee'
    entry_point_nav_page = 'TeamPage'
    entry_point_needs_event = False
    model = Nomination
    template_name = 'team_pages/nominations/nomination_list.html'
    context_object_name = 'nominations'

    def get_queryset(self):
        return Nomination.objects.all().order_by('-nomination_date')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        nominations = self.get_queryset()
        context |= {
            'new': nominations.filter(status=Nomination.Status.NEW),
            'accepted': nominations.filter(status=Nomination.Status.ACCEPTED),
            'rejected': nominations.filter(status=Nomination.Status.REJECTED),
            'completed': nominations.filter(status=Nomination.Status.COMPLETED),
            'complete': nominations.filter(status=Nomination.Status.COMPLETED),
        }
        return context


class NominationView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    login_url = reverse_lazy('user_management:login')
    redirect_field_name = 'next'
    permission_required = 'GarageSale.is_trustee'
    model = Nomination
    template_name = 'team_pages/nominations/nomination_view.html'
    context_object_name = 'nomination'

    def post(self, request, *args, **kwargs):
        nomination = self.get_object()
#        print(nomination.status, request.POST)
        match nomination.status :
            case Nomination.Status.NEW if 'accept' in request.POST:
                nomination.status = Nomination.Status.ACCEPTED
            case Nomination.Status.NEW if request.POST.get('reject'):
                nomination.status = Nomination.Status.REJECTED
                nomination.reason = request.POST.get('rejection_reason', '')
            case Nomination.Status.ACCEPTED if request.POST.get('complete'):
                nomination.status = Nomination.Status.COMPLETED
            case Nomination.Status.ACCEPTED if request.POST.get('reject'):
                nomination.status = Nomination.Status.REJECTED
                nomination.reason = request.POST.get('rejection_reason', '')
            case Nomination.Status.ACCEPTED if request.POST.get('reconsider'):
                nomination.status = Nomination.Status.NEW
            case Nomination.Status.REJECTED if request.POST.get('reconsider'):
                nomination.status = Nomination.Status.NEW
                nomination.reason = ''
            case _:
                raise Exception(f"Unexpected nomination status: {nomination.status} - {request.POST}")
        nomination.save()
        return redirect('NominationsList')
