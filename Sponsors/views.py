from django.shortcuts import render

# Create your views here.

from django.template.response import TemplateResponse
from .models import Sponsor

#TODO - Link Sponsors page to the main menu


def sponsor_list(request):
    sponsors = Sponsor.objects.filter(event__id = request.current_event.id)
    return TemplateResponse(request,'view_sponsors.html',
                            context={'sponsors': sponsors,
                                     'socials':['website','facebook','twitter','instagram'] } )