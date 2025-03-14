from django.shortcuts import render

# Create your views here.

from django.template.response import TemplateResponse
from .models import Sponsor


def social_media_items():
    return ['website','facebook','instagram']


def sponsor_list(request):
    sponsors = Sponsor.objects.filter(event__id = request.current_event.id)
    return TemplateResponse(request,'view_sponsors.html',
                            context={'sponsors': sponsors,
                                     'socials':social_media_items() } )