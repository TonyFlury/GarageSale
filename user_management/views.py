from uuid import uuid1

from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login as login_user
from django.http import HttpResponseServerError, HttpResponse, HttpRequest
from django.core.mail import send_mail
from django.shortcuts import redirect, reverse
from django.template.response import TemplateResponse
from django.utils.html import escape
from django.db import transaction
from django.shortcuts import render, resolve_url
from django.views.generic import View

from .forms import RegistrationForm, LoginForm, PasswordChangeForm, ResetPasswordApplyForm, PasswordResetForm
from .models import UserVerification, PasswordResetApplication

from .apps import appsettings, settings
from django.contrib.auth import get_user, logout, update_session_auth_hash

import logging

logger = logging.Logger('user_management-views', logging.DEBUG)
handler = logging.FileHandler('./debug.log')
handler.setLevel(logging.DEBUG)
logger.addHandler(handler)


# ToDo - show password Help on registration, and validate password format


def logoff(incoming_request: HttpRequest):
    redirect_path = incoming_request.GET.get('redirect', '/')
    user = get_user(incoming_request)
    if not user.is_authenticated:
        return HttpResponseServerError()
    else:
        logout(incoming_request)

    return redirect(redirect_path)


class UserRegistration(View):
    email_template = "email/verify_email.html"

    def get(self, incoming_request):
        redirect_url = incoming_request.GET.get('redirect', '/')

        form = RegistrationForm()
        return TemplateResponse(incoming_request,
                                'generic_with_form.html',
                                context=form.form_context(redirect_url=redirect_url))

    def post(self, incoming_request):

        logger.debug(f"user registration received")
        redirect_url = incoming_request.GET.get('redirect', '/')

        # Build a form instance for validation purposes.
        form = RegistrationForm(incoming_request.POST)

        if not form.is_valid():
            return TemplateResponse(incoming_request,
                                    'generic_with_form.html',
                                    context=form.form_context(redirect_url=redirect_url))
        if form.is_valid():
            logger.debug(f"user registration received for {form.cleaned_data['email']}")

            # Begin safe with a transaction
            with transaction.atomic():
                # Create a new but inactive user_management

                try:
                    user = User.objects.get(email=form.cleaned_data['email'])
                except User.DoesNotExist:
                    user = None

                if user and user.is_active:
                    form.add_error(None, 'This user already exists - did you mean to login in')
                    return TemplateResponse(incoming_request,
                                            'generic_with_form.html',
                                            context=form.form_context(redirect_url=redirect_url))

                if user and (not user.is_active):
                    new_user = user
                else:
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

            url = (incoming_request.build_absolute_uri(
                location=reverse("user_management:verify", kwargs={"uuid": secret})) +
                   "?" + escape(f'redirect={redirect_url}'))

            # Send email to the new user_management with a link to the verification view

            base_url = incoming_request.scheme + r'://' + incoming_request.get_host()

            html_content = TemplateResponse(incoming_request, self.email_template,
                                            context={'base_url': base_url,
                                                     'url': url}).rendered_content

            # Extract Application settings from the APPS_SETTING dictionary with defaults
            site_name = appsettings().get('user_management', {}).get('SITE_NAME', '')
            sender = appsettings().get('user_management', {}).get('EMAIL_SENDER', None)
            sender = sender if sender else settings.EMAIL_HOST_USER

            send_mail(subject=f'{site_name}: Verify email address for your new account',
                      message=html_content,
                      from_email=f'{sender}',
                      recipient_list=[form.cleaned_data["email"]],
                      html_message=html_content)

            return TemplateResponse(incoming_request, 'generic_response.html',
                                    context={'msg': 'Thank you for registering. '
                                                    'Please check your email for a verification link which will '
                                                    'complete the registration process'})


def user_verify(request, uuid=None):
    if request.method != 'GET':
        return HttpResponseServerError(request)
    redirect_url = request.GET.get('redirect', '/')

    logger.debug(f"user-verify received uuid : {uuid}")
    verify = UserVerification.objects.get(uuid=uuid)

    logger.debug(f" this record belongs too : {verify.email}")

    # TODO - add timeout logic

    user = User.objects.get(email=verify.email)
    user.is_active = True
    user.save()
    verify.delete()

    return redirect(redirect_url)


class Login(View):
    def get(self, request):
        """Render a new blank form"""

        redirect_url = request.GET.get('redirect', '/')
        form = LoginForm()

        rest_url = resolve_url('user_management:reset_password_application')
        return TemplateResponse(request,
                                'generic_with_form.html',
                                context=form.form_context(redirect_url=redirect_url))

    def post(self, request):
        """deal with the submitted form"""
        redirect_url = request.GET.get('redirect', '/')
        form_inst = LoginForm(request.POST)
        if not form_inst.is_valid():
            return TemplateResponse(request,
                                    'generic_with_form.html',
                                    context=form_inst.form_context(redirect_url=redirect_url))

        try:
            user_inst = User.objects.get(email=form_inst.cleaned_data['email'])
        except User.DoesNotExist:
            form_inst.add_error(None, "Invalid User/password combination")
            return TemplateResponse(request,
                                    'generic_with_form.html',
                                    context=form_inst.form_context(redirect_url=redirect_url))

        # If the user is inactive this has been added as the result of an 'anonymous' application
        if not user_inst.is_active:
            form_inst.add_error(None, "This user doesn't exist - did you mean to register instead")
            return TemplateResponse(request,
                                    'generic_with_form.html',
                                    context=form_inst.form_context(redirect_url=redirect_url))

        # Sign this user in
        user = authenticate(username=form_inst.cleaned_data['email'],
                            password=form_inst.cleaned_data['password'])

        if user is None:
            form_inst.add_error(None, 'Invalid User/password combination')
            return TemplateResponse(request,
                                    'generic_with_form.html',
                                    context=form_inst.form_context(redirect_url=redirect_url))
        else:
            login_user(request, user)
            return redirect(redirect_url)


class ChangePassword(View):
    def get(self, request: HttpRequest):
        redirect_url = request.GET.get('redirect', '/')

        if not request.user.is_authenticated:
            return redirect(resolve_url('user_management:login') + f'?redirect={redirect_url}')

        form = PasswordChangeForm()
        return TemplateResponse(request,
                                'generic_with_form.html',
                                context=form.form_context(redirect_url=redirect_url))

    def post(self, request: HttpRequest):
        redirect_url = request.GET.get('redirect', '/')

        if not request.user.is_authenticated:
            return redirect(resolve_url('user_management:login') + f'?redirect={redirect_url}')

        form = PasswordChangeForm(request.POST)

        if not form.is_valid():
            return TemplateResponse(request,
                                    'generic_with_form.html',
                                    context=form.form_context(redirect_url=redirect_url))

        old_pwd = form.cleaned_data['old_password']

        if not request.user.check_password(old_pwd):
            form.add_error('old_password', 'Provide the correct current password')
            return TemplateResponse(request,
                                    'generic_with_form.html',
                                    context=form.form_context(redirect_url=redirect_url))

        if form.cleaned_data['new_password1'] != form.cleaned_data['new_password2']:
            form.add_error('new_password2', 'New password entries must be the same')
            return TemplateResponse(request,
                                    'generic_with_form.html',
                                    context=form.form_context(redirect_url=redirect_url))

        request.user.set_password(form.cleaned_data['new_password1'])
        request.user.save()

        update_session_auth_hash(request, request.user)

        return TemplateResponse(request,
                                'generic_response.html',
                                context={'redirect': redirect_url,
                                         'msg': 'Your password has now been changed successfully'})


class ResetPasswordApply(View):
    def get(self, request):
        redirect_url = request.GET.get('redirect', '/')
        form = ResetPasswordApplyForm()
        return TemplateResponse(request,
                                'generic_response.html',
                                context=form.form_context(redirect_url=redirect_url))

    def post(self, request):
        # Send email to the user with a link to the verification view
        email_template = 'email/password_reset_email.html'
        redirect_url = request.GET.get('redirect', '/')

        form = ResetPasswordApplyForm(request.POST)
        if not form.is_valid():
            return TemplateResponse(request,
                                    'generic_with_form.html',
                                    context=form.form_context(redirect_url=redirect_url))

        try:
            user = User.objects.get(username=form.cleaned_data['email'])
        except User.DoesNotExist:
            form.add_error('email', 'No user exists with this email address')
            return TemplateResponse(request,
                                    'generic_with_form.html',
                                    context=form.form_context(redirect_url=redirect_url))

        base_url = request.scheme + r'://' + request.get_host()
        secret = uuid1()
        url = (request.build_absolute_uri(
            location=reverse("user_management:reset_password", kwargs={"uuid": secret})) +
               "?" + escape(f'redirect={redirect_url}'))

        pwd_reset = PasswordResetApplication(user=user,
                                             uuid=secret)
        pwd_reset.save()

        html_content = TemplateResponse(request, email_template,
                                        context={'base_url': base_url,
                                                 'url': url}).rendered_content

        site_name = appsettings().get('user_management', {}).get('SITE_NAME', '')
        sender = appsettings().get('user_management', {}).get('EMAIL_SENDER', None)
        sender = sender if sender else settings.EMAIL_HOST_USER

        send_mail(subject=f'{site_name}: Password reset requested',
                  message=html_content,
                  from_email=f'{sender}',
                  recipient_list=[form.cleaned_data["email"]],
                  html_message=html_content)

        return TemplateResponse(request, 'generic_response.html',
                                context={'msg': 'A Password reset email has been sent to you. '
                                                'Please check your email and click the button/link.'})


class PasswordReset(View):
    def get(self, request, uuid):
        redirect_url = request.GET.get('redirect', '/')

        try:
            application = PasswordResetApplication.objects.get(uuid=uuid)
        except PasswordResetApplication.DoesNotExist:
            return HttpResponseServerError(f'Received a password reset with an unknown uuid {uuid}')

        form = PasswordResetForm()
        return TemplateResponse(request,
                                'generic_with_form.html',
                                context=form.form_context(uuid, redirect_url=redirect_url))

    def post(self, request, uuid):
        redirect_url = request.GET.get('redirect', '/')

        form = PasswordResetForm(request.POST)
        if not form.is_valid():
            return TemplateResponse(request,
                                    'generic_with_form.html',
                                    context=form.form_context(redirect_url=redirect_url))

        try:
            application = PasswordResetApplication.objects.get(uuid=uuid)
        except PasswordResetApplication.DoesNotExist:
            return HttpResponseServerError(f'Received a password reset with an unknown uuid {uuid}')

        user: User = application.user

        if form.cleaned_data['new_password1'] != form.cleaned_data['new_password2']:
            form.add_error('new_password2', 'The passwords provided must be the same as each other')
            return TemplateResponse(request,
                                    'generic_with_form.html',
                                    context=form.form_context(uuid, redirect_url=redirect_url))

        if user.check_password(form.cleaned_data['new_password1']):
            form.add_error(None, 'Your new password must be different from your current password')
            return TemplateResponse(request,
                                    'generic_with_form.html',
                                    context=form.form_context(uuid, redirect_url=redirect_url))

        user.set_password(form.cleaned_data['new_password1'])
        user.save()
        update_session_auth_hash(request, request.user)

        application.delete()

        return TemplateResponse(request, 'generic_response.html',
                                context={'msg': 'Your password has now been changed.',
                                         'redirect': redirect_url})

# ToDo - Refactor the templates into a Generic form and Generic message type forms
