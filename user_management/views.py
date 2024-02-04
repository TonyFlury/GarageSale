from uuid import uuid1

from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login as login_user
from django.http import HttpResponseServerError
from django.core.mail import send_mail
from django.shortcuts import redirect, reverse
from django.template.response import TemplateResponse
from .forms import Registration, LoginForm
from .models import UserVerification
from .apps import appsettings, settings
from django.utils.html import escape
from django.db import transaction
from django.core.exceptions import ValidationError

import logging

logger = logging.Logger('user_management-views', logging.DEBUG)
handler = logging.FileHandler('./debug.log')
handler.setLevel(logging.DEBUG)
logger.addHandler(handler)


def user_registration_submission(request):
    if request.method != "POST":
        return HttpResponseServerError(request)

    logger.debug(f"user registration received")

    # Build a form instance for validation purposes.
    form = Registration(request.POST)

    if not form.is_valid():
        raise ValidationError(form.errors)

    if form.is_valid():
        # TODO  -Might want to check for duplication here

        logger.debug(f"user registration received for {form.cleaned_data['email']}")

        # Begin safe with a transaction
        with transaction.atomic():
            # Create a new but inactive user_management
            new_user = User.objects.create_user(username=form.cleaned_data['email'],
                                                email=form.cleaned_data['email'],
                                                first_name=form.cleaned_data['first_name'],
                                                last_name=form.cleaned_data['last_name'],
                                                password=form.cleaned_data['password'],
                                                is_active=False)
            secret = uuid1()

            verify = UserVerification(email=form.cleaned_data['email'], uuid=secret)
            new_user.save()
            verify.save()

        redirect_path = form.cleaned_data["redirect"]
        redirect_path = redirect_path if redirect_path else "home"

        url = (request.build_absolute_uri(
                location=reverse( "user_management:verify", kwargs={"uuid":secret}) ) +
               "?" + escape(f'redirect={reverse(redirect_path)}'))

        logger.debug(f"email includes {url}")

        # Send email to the new user_management with a link to the verification view
        email_template = form.cleaned_data['email_template']

        base_url = request.scheme + r'://' + request.get_host()

        html_content = TemplateResponse(request, email_template,
                                        context={'base_url': base_url,
                                                 'url': url}).rendered_content

        # Extract Application settings from the APPS_SETTING dictionary with defaults
        site_name = appsettings().get('user_management', {}).get('SITE_NAME', '')
        sender = appsettings().get('user_management', {}).get('EMAIL_SENDER', None)
        sender = sender if sender else settings.EMAIL_HOST_USER

        send_mail( subject=f'{site_name}: Verify email address for your new account',
                   message= html_content,
                   from_email= f'{sender}',
                   recipient_list= [form.cleaned_data["email"]],
                   html_message=html_content)

        logger.debug(f'redirect from user submission to {form.cleaned_data["next"]}')

        return redirect(form.cleaned_data['next'])


def user_verify(request, uuid=None):
    if request.method != 'GET':
        return HttpResponseServerError(request)

    logger.debug(f"user-verify received uuid : {uuid}")
    verify = UserVerification.objects.get(uuid=uuid)

    logger.debug(f" this record belongs too : {verify.email}")

    #TODO - add timeout logic

    user = User.objects.get(email=verify.email)
    user.is_active = True
    user.save()
    verify.delete()

    return redirect(reverse("home"))


def login(request):
    """Deal with a request from a login form"""
    if request.method != "POST":
        return HttpResponseServerError(request)

    form_inst = LoginForm(request.POST)
    if not form_inst.is_valid():
        raise ValidationError(form_inst.errors)

    user = authenticate( username=form_inst.cleaned_data['email'],
                         password=form_inst.cleaned_data['password'] )

    if user is None:
        raise ValidationError( "Invalid username/password_combination", code='InvalidCredentials')
    else:
        login_user(request, user)
        return redirect(form_inst.cleaned_data['redirect'])