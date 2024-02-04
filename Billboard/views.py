from django.shortcuts import render

# Create your views here.

from django.views import View
from django.contrib.auth.models import User
from django.http import HttpResponse, HttpResponseServerError
from django.shortcuts import render, reverse

from .forms import BillboardApplicationForm

def billboard_complete(request):
    pass


class BillBoardApply(View):
    def get(self, request):
        if request.GET['action'] == 'apply':
            u = User.objects.get(username=request.user.username)
            form = BillboardApplicationForm(initial={'email':request.user.email,
                                                     'name': f'{u.first_name} {u.last_name}',
                                                     })
            action = reverse('Billboard:apply') + '?=' + request.GET['redirect']
            return render(request, template_name='billboard_apply.html',
                          context={'form': form,
                                   'action': action,
                                   'redirect': request.GET['redirect']})
