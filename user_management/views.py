import datetime
from datetime import datetime as dt
import logging
from typing import Type
from uuid import uuid1
import io

import weasyprint
from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.staticfiles import finders
from django.template import Template, Context
from django.template.loader import get_template
from django.templatetags.static import static
from django.utils import timezone, encoding
from django.contrib.auth.models import User
from django.contrib.auth import login as login_user
from django.http import HttpResponseServerError, HttpRequest, Http404, HttpResponse
from django.core.mail import send_mail
from django.core.mail import EmailMultiAlternatives
from django.shortcuts import redirect, reverse
from django.template.response import TemplateResponse
from django.utils.html import escape
from django.db import transaction
from django.shortcuts import resolve_url
from django.views.generic import View, UpdateView
from django.core.exceptions import ObjectDoesNotExist, ValidationError, PermissionDenied
from django.contrib.auth import authenticate

from TeamPageFramework.entry_point import EntryPointMixin
from . import forms
from . import models
from .models import RegistrationVerifier, GuestVerifier, PasswordResetApplication, UserVerification, UserExtended, \
    AdditionalData, TeamMember

from .apps import appsettings, settings
from django.contrib.auth import get_user_model, login, logout, update_session_auth_hash

from .models import RegistrationVerifier
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# ToDo - show password Help on registration, and validate password format
# ToDo - test password Reset stuff
# ToDo - Remove old templates - retest first
# ToDo - Rename the views - they are confusing

def send_register_verification_email(incoming_request, email, url):
    # Send email to the new user_management with a link to the verification view
    email_template = "email/verify_email.html"

    base_url = incoming_request.scheme + r'://' + incoming_request.get_host()
    html_content = TemplateResponse(incoming_request, email_template,
                                    context={'base_url': base_url,
                                             'url': url}).rendered_content
    # Extract Application settings from the APPS_SETTING dictionary with defaults
    site_name = appsettings().get('user_management', {}).get('SITE_NAME', '')
    sender = appsettings().get('user_management', {}).get('EMAIL_SENDER', None)
    sender = sender if sender else settings.EMAIL_HOST_USER
    non_html = (f'Thank for registering for a user account on {site_name}\n'
                f'To confirm your registration - please copy/paste the following link into your browser:\n'
                f'{url}\n'
                f'This link will expire in ')
    msg = EmailMultiAlternatives(subject=f'{site_name}: Verify registration of your account',
                                 from_email=f'{sender}',
                                 to=[email])
    msg.attach_alternative(non_html, 'text/plain')
    msg.attach_alternative(html_content, 'text/html')
    msg.send()


def send_guest_verification_email(request, email=None, short_code=None, template=None,
                                  sender=None):
    """Send an email with the one time code"""
    html_content = TemplateResponse(
        request=request,
        template=template,
        context={'code': short_code.short_code,
                 'lifetime': short_code.short_code_lifetime,
                 },
    ).rendered_content

    site_name = appsettings().get('user_management', {}).get('SITE_NAME', '')
    sender = sender if sender else appsettings().get('user_management', {}).get('EMAIL_SENDER', None)
    sender = sender if sender else settings.EMAIL_HOST_USER

    msg = EmailMultiAlternatives(subject=f'{site_name}: Guest Account One time code',
                                 from_email=f'{sender}',
                                 to=[email])
    msg.attach_alternative(f'Your one time code is {short_code.short_code} - '
                           f'please enter this value into the website',
                           'text/plain')
    msg.attach_alternative(html_content, 'text/html')
    msg.send()


def guest_error(incoming_request, short_code_id=None):
    """View to display error page for guest logins"""
    next = incoming_request.GET.get('next', '/')

    try:
        code_inst = GuestVerifier.objects.get(pk=short_code_id)
    except GuestVerifier.DoesNotExist:
        logger.info(f'Invalid Short Code {short_code_id} sent to error page !')
        redirect_url = incoming_request.GET.get('next', '/')
        return redirect( reverse('user_management:guest_application') + '?next=' + redirect_url )


    match code_inst.reason_code:
        case 'expired':
            pre_form = 'Your existing short code expired'
        case 'entry_error':
            pre_form = 'You failed to enter the correct short code after 3 attempts.'
        case _:
            pre_form = ''

    form = forms.GuestApplicationError()

    return TemplateResponse(incoming_request,
                            'generic_forms/generic_with_form.html',
                            context=form.form_context(
                                action_path=resolve_url('user_management:resend', short_code_id=short_code_id),
                                pre_form=pre_form,
                                next=next))


def resend_short_code(incoming_request, short_code_id=None):
    """"Simple view to resend a new short-code - use existing short_code
        as the original data for the next
    """
    email_template = "email/guest_short_code-email.html"

    next_url = incoming_request.GET.get('next', '/')
    try:
        inst: GuestVerifier = GuestVerifier.objects.get(id=short_code_id)
    except GuestVerifier.DoesNotExist:
        logger.info(f'Invalid Short Code {short_code_id} sent to resend page !')
        redirect_url = incoming_request.GET.get('next', '/')
        return redirect( reverse('user_management:guest_application') + '?next=' + redirect_url )

    email = inst.email
    GuestVerifier.remove_expired(email=email, _any=True)

    new_inst = GuestVerifier.add_guest_verifier(email=email)
    new_inst.reason_code='resend'
    new_inst.save()

    logger.info(f'Resending code for {email!r} - with {new_inst.short_code!r} - email sent')
    send_guest_verification_email(incoming_request, email=email, short_code=new_inst, template=email_template)

    return redirect(reverse('user_management:input_short_code',
                            kwargs={'short_code_id': new_inst.pk}) + f'?next={next_url}')


def resend_registration_link(incoming_request, uuid):
    """"Simple view to resend a new short-code - use existing short_code
        as the original data for the next
    """
    next_url = incoming_request.GET.get('next', '/')

    verifier_inst = RegistrationVerifier.objects.get(uuid=uuid)

    user_model:Type[UserExtended|AbstractBaseUser] = get_user_model()
    try:
        user = user_model.objects.get(email=verifier_inst.email)
    except user_model.DoesNotExist:
        raise ObjectDoesNotExist('User does not exist')

    email = verifier_inst.email
    if user.is_guest:
        try:
            additional = verifier_inst.AdditionalData.objects.values().get()
        except AdditionalData.DoesNotExist:
            raise ObjectDoesNotExist('Registration AdditionalData does not exist')
    else:
        additional = {}

    verifier_inst.delete()

    verifier_inst = RegistrationVerifier.add_registration_verifier(user=user, **additional)

    url = verifier_inst.link_url(request=incoming_request, next_url=next_url)

    send_register_verification_email(email=verifier_inst.email, incoming_request=incoming_request, url=url)

    return TemplateResponse(incoming_request, 'generic_forms/generic_response.html',
                            context={'msg': 'A new registration link has been sent.<br>'
                                            f'Please check your email {UserRegistration.obfuscate_email(verifier_inst)} for a verification link which will '
                                            'complete the registration process.<br>'
                                     'If the email doesn\'t arrive - please check your spam email folder'})




class GuestApplication(View):
    email_template = "email/guest_short_code-email.html"

    def get(self, incoming_request):
        redirect_url = incoming_request.GET.get('next', '/')

        form = forms.GuestRequestForm()
        return TemplateResponse(incoming_request,
                                template='generic_forms/generic_with_form.html',
                                context=form.form_context(next=redirect_url))

    def post(self, incoming_request: HttpRequest):
        next = incoming_request.GET.get('next', '/')

        form = forms.GuestRequestForm(incoming_request.POST)
        if not form.is_valid():
            return TemplateResponse(incoming_request,
                                    'generic_forms/generic_with_form.html',
                                    context=form.form_context(next=next)
                                    )

        email = form.cleaned_data['email']

        # We know the data is a valid email - remove old entries and add a new entry
        GuestVerifier.remove_expired(email=email)
        code = GuestVerifier.add_guest_verifier(email=email)

        send_guest_verification_email(incoming_request,
                                      email=form.cleaned_data['email'],
                                      short_code=code,
                                      template=self.email_template)
        logger.info(f'Guest Application - for {email!r} - with {code.short_code!r} instance {code.pk=} - email sent')
        return redirect(resolve_url('user_management:input_short_code', short_code_id=code.pk) + f'?next={next}')


class InputShortCode(View):

    @staticmethod
    def _obfuscate_email(short_code_inst: GuestVerifier) -> str:
        email = short_code_inst.email
        tld = email.split('.')[-1]
        name, domain = email.split('@')[0], email.split('@')[1]
        return name[0:4].rjust(len(name), '*') + '@' + domain[0:4].rjust(len(domain), '*') + '.' + tld

    def get(self, incoming_request, short_code_id):
        next = incoming_request.GET.get('next', '/')
        logger.info(f'InputShortCode (GET method)- {short_code_id=}')
        try:
            code_inst = GuestVerifier.objects.get(pk=short_code_id)
        except GuestVerifier.DoesNotExist:
            logger.error(f'Unknown {short_code_id=}')
            raise ObjectDoesNotExist(f'Received Invalid ShortCode pk {short_code_id} ')

        if code_inst.reason_code == 'resend':
            logger.info(f'Resent code for {code_inst.email}')
            pre_form = 'A new code has been sent by email'
            code_inst.reason_code = ''
            code_inst.save()
        else:
            pre_form = ""

        form = forms.InputShortCodeForm(data={'email': code_inst.email})
        logger.info(f'InputShortCode - Prompting for short code for {code_inst.email=!r} instance {code_inst.pk=}')
        return TemplateResponse(request=incoming_request,
                                template='identify/ShortCodeInput.html',
                                context={'form': form,
                                         'pre_form': pre_form,
                                         'email': code_inst.email,
                                         'action': resolve_url('user_management:input_short_code',
                                                               short_code_id=short_code_id) + f'?next={next}',
                                         'resend_url': resolve_url('user_management:resend',
                                                                   short_code_id=short_code_id) + f'?next={next}',
                                         'obfuscated_email': self._obfuscate_email(code_inst)})

    def post(self, incoming_request: HttpRequest, short_code_id):
        next = incoming_request.GET.get('next', '/')

        logger.info(f'InputShortCode - Looking for the Guest verifier {short_code_id=}')
        try:
            code_inst = GuestVerifier.objects.get(pk=short_code_id)
        except GuestVerifier.DoesNotExist:
            raise ObjectDoesNotExist(f'No such GuestVerifierObject : {short_code_id}')

        form = forms.InputShortCodeForm(data=incoming_request.POST)
        if not form.is_valid():
            logger.info(f'InputShortCode - invalid form input {form.cleaned_data['short_code']=}')
            return TemplateResponse(request=incoming_request,
                                    template='identify/ShortCodeInput.html',
                                    context={'form': form,
                                             'action': resolve_url('user_management:input_short_code',
                                                                   short_code_id=short_code_id) + f'?next={next}',
                                             'obfuscated_email': self._obfuscate_email(code_inst)})

        if form.cleaned_data['email'] != code_inst.email:
            logger.error(f'InputShortCode - email address in form doesn\'t match expected email from db {form.cleaned_data["email"]=!r} {code_inst.email=!r}')
            raise ValidationError(f'email address for guest request don\'t match')

        # The data matched - ie the forms is valid - check for expiry
        if code_inst.is_time_expired():
            code_inst.reason_code = 'expired'
            code_inst.save()
            logger.error(f'InputShortCode - Guest verifier for {code_inst.email} has expired - {code_inst.expiry_timestamp=}')
            return redirect(resolve_url('user_management:guest_error', short_code_id=code_inst.pk) + f'?next={next}')

        if form.cleaned_data['short_code'] != code_inst.short_code:
            logger.error(f'InputShortCode - Incorrect input - {form.cleaned_data['short_code']=!r} != {code_inst.short_code=!r}')
            code_inst.retry_count -= 1
            code_inst.save()

            # Only re-show the forms if the retry count hasn't hit zero
            if code_inst.retry_count > 0:
                # Build a blank forms

                form = forms.InputShortCodeForm(data={'email': code_inst.email})
                form.add_error(None, 'Short code Incorrect - please try again')

                return TemplateResponse(request=incoming_request,
                                        template='identify/ShortCodeInput.html',
                                        context={'form': form,
                                                 'action': resolve_url('user_management:input_short_code',
                                                                       short_code_id=short_code_id) + f'?next={next}',
                                                 'obfuscated_email': self._obfuscate_email(code_inst),
                                                 'retry_count': code_inst.retry_count,
                                                 'max_retry': code_inst.max_retry}, )
            else:
                logger.error(f'InputShortCode - Too many Incorrect inputs : expecting {code_inst.short_code=!r}')
                code_inst.reason_code = 'entry_error'
                code_inst.save()
                return redirect(resolve_url('user_management:guest_error', short_code_id=code_inst.pk)
                                + f'?next={next}')

        logger.info(f'InputShortCode - Correct input - received {code_inst.short_code=!r} for {code_inst.pk=}')

        user_model:Type[UserExtended|AbstractBaseUser] = get_user_model()
        # The code is correct and no expired - redirect to the 'next' url
        # Create a guest user if necessary
        try:
            user_inst = user_model.objects.get(email=code_inst.email)
        except user_model.DoesNotExist:
            user_inst = None

        # Create a guest user account if necessary - allow a two hour time out on guest users
        if user_inst:
            logger.info(f'InputShortCode - Existing user - marking them as verified so they can login - {code_inst.email=!r}')
            user_inst.is_verified=True
            try:
                user_inst.save()
            except Exception as e:
                raise e from None

            logger.info(f'InputShortCode - Make the user logged in for 2 hours - {code_inst.email=!r}')
            login(request=incoming_request, user=user_inst)
            try:
                incoming_request.session.set_expiry(timezone.now() + datetime.timedelta(hours=2))
            except AttributeError:
                raise AttributeError('failed to set session expiry')

            GuestVerifier.add_guest_verifier(email=code_inst.email).delete()

        else:
            logger.info(f'InputShortCode - Creating a guest user entry for - {code_inst.email=!r} and log them in for 2 hours')
            user = user_model.objects.create_guest_user(email=code_inst.email, is_verified=True)
            login(request=incoming_request, user=user)
            try:
                incoming_request.session.set_expiry(timezone.now() + datetime.timedelta(hours=2))
            except AttributeError:
                raise AttributeError('failed to set session expiry')

            GuestVerifier.objects.filter(email=code_inst.email).delete()

        return redirect(next)


def identify(incoming_request: HttpRequest):
    """Render a simple login, login as Guest button sets"""
    next_url = incoming_request.GET.get('next', '/')
    return TemplateResponse(incoming_request, template='identify/identify.html',
                            context={
                                'next': next_url})


def logoff(incoming_request: HttpRequest):
    redirect_path = incoming_request.GET.get('redirect', '/')
    user = incoming_request.user
    if not user.is_authenticated:
        return HttpResponseServerError()
    else:
        logout(incoming_request)

    return redirect(redirect_path)


class UserRegistration(View):
    email_template = "email/verify_email.html"

    @staticmethod
    def obfuscate_email(verifier: RegistrationVerifier) -> str:
        email = verifier.email
        name, domain = email.split('@')
        *domain, tld = domain.split('.')
        domain = '.'.join(domain)
        return name[0:4].ljust(len(name), '*') + '@' + domain[0:4].ljust(len(domain), '*') + '.' + tld

    @staticmethod
    def get(incoming_request):
        next_url = incoming_request.GET.get('next', '/')

        form = forms.RegistrationForm()
        return TemplateResponse(incoming_request,
                                'generic_forms/generic_with_form.html',
                                context=form.form_context(next_url=next_url))

    def post(self, incoming_request):

        next_url = incoming_request.GET.get('next', '/')

        # Build a forms instance for validation purposes.
        form = forms.RegistrationForm(incoming_request.POST)

        if not form.is_valid():
            return TemplateResponse(incoming_request,
                                    'generic_forms/generic_with_form.html',
                                    context=form.form_context(next_url=next_url))

        if form.cleaned_data['password'] != form.cleaned_data['password_repeat']:
            form.add_error('password', 'Passwords do not match')
            return TemplateResponse(incoming_request,
                                    'generic_forms/generic_with_form.html',
                                    context=form.form_context(next_url=next_url))

        # Begin safe with a transaction
        with transaction.atomic():
            # Create a new but inactive user_management

            user_model: Type[UserExtended | AbstractBaseUser] = get_user_model()

            try:
                user = user_model.objects.get(email=form.cleaned_data['email'])
            except user_model.DoesNotExist:
                user = None

            if user and not user.is_guest:
                form.add_error(None, 'This user already exists - did you mean to login in')
                return TemplateResponse(incoming_request,
                                        'generic_forms/generic_with_form.html',
                                        context=form.form_context(next_url=next_url))

            if user:
                if user.is_guest:
                    new_user = user
            else:
                new_user = user_model.objects.create_user(email=form.cleaned_data['email'],
                                                                first_name=form.cleaned_data['first_name'],
                                                                last_name=form.cleaned_data['last_name'],
                                                                phone=form.cleaned_data['phone'],
                                                                is_active=False)
                new_user.set_password(form.cleaned_data['password'])
                new_user.save()

            verify = RegistrationVerifier.add_registration_verifier(
                                                user=new_user,
                                                password=form.cleaned_data['password'],
                                                first_name=form.cleaned_data['first_name'],
                                                last_name=form.cleaned_data['last_name'],
                                                phone=form.cleaned_data['phone'])

            url = verify.link_url(request=incoming_request, next_url=next_url)

            send_register_verification_email(incoming_request, new_user.email, url)

            return TemplateResponse(incoming_request, 'generic_forms/generic_response.html',
                                    context={'msg': 'Thank you for registering. '
                                                    f'Please check your email {self.obfuscate_email(verify)} for a verification link which will '
                                                    'complete the registration process'})


def user_verify(request, uuid=None):
    """View triggered when user clicks the link to verify registration"""
    if request.method != 'GET':
        return HttpResponseServerError(request)
    next_url = request.GET.get('next', '/')

    try:
        verify = RegistrationVerifier.objects.get(uuid=uuid)
    except RegistrationVerifier.DoesNotExist:
        return TemplateResponse(request, template='generic_forms/generic_response.html',
                                context={'redirect': next_url,
                                         'msg': """
                                         This verification link has already been used, and the user account is ready to be used"""})

    if verify.expiry_timestamp < timezone.now():
        return TemplateResponse(request, template='generic_forms/generic_response.html',
                                context={'redirect': reverse('user_management:resend_verify',
                                                             kwargs={'uuid': verify.uuid}) + f"?next={next_url}",
                                         'msg': "This verification link has expired - pleased wait for a few seconds to get a new code"})

    user = get_user_model().objects.get(email=verify.email)
    if user.is_guest:
        user.first_name = verify.AdditionalData.first_name
        user.last_name = verify.AdditionalData.last_name
        user.phone = verify.AdditionalData.phone
        user.set_password(verify.AdditionalData.password)
        user.is_guest = False

    user.is_verified = True
    user.is_active = True

    user.save()
    verify.delete()

    return redirect(next_url)


class Login(View):
    @staticmethod
    def get(request):
        """Render a new blank forms"""

        next = request.GET.get('next', '/')
        form = forms.LoginForm()

        return TemplateResponse(request,
                                'generic_forms/generic_with_form.html',
                                context=form.form_context(
                                    reset_path='user_management:reset_password_application',
                                    next=next))

    @staticmethod
    def post(request):
        """deal with the submitted forms"""
        next_url = request.GET.get('next', '/')
        form_inst = forms.LoginForm(request.POST)
        if not form_inst.is_valid():
            return TemplateResponse(request,
                                    'generic_forms/generic_with_form.html',
                                    context=form_inst.form_context(
                                    reset_path='user_management:reset_password_application',
                                    next=next_url))

        try:
            user_model:Type[UserExtended|AbstractBaseUser] = get_user_model()
            user_inst:UserExtended = user_model.objects.get(email=form_inst.cleaned_data['email'])
        except get_user_model().DoesNotExist:
            form_inst.add_error(None, "Invalid User/password combination")
            return TemplateResponse(request,
                                    'generic_forms/generic_with_form.html',
                                    context=form_inst.form_context(
                                        reset_path='user_management:reset_password_application',
                                        next=next_url))

        if user_inst.is_guest:
            form_inst.add_error(None, "This is only a Guest account currently - please fully register this account to be able to use the login")
            return TemplateResponse(request,
                                    'generic_forms/generic_with_form.html',
                                    context=form_inst.form_context(
                                        reset_path='user_management:reset_password_application',
                                        next=next_url))

        if not user_inst.is_verified:
            form_inst.add_error(None, "User account not verified - please check your email for the verification link")
            return TemplateResponse(request,
                                    'generic_forms/generic_with_form.html',
                                    context=form_inst.form_context(
                                        reset_path='user_management:reset_password_application',
                                        next=next_url))

        # Sign this user in
        user = authenticate(username=form_inst.cleaned_data['email'],
                            password=form_inst.cleaned_data['password'])

        if user is None:
            form_inst.add_error(None, 'Invalid User/password combination')
            return TemplateResponse(request,
                                    'generic_forms/generic_with_form.html',
                                    context=form_inst.form_context(next=next_url))
        else:
            login_user(request, user)
            return redirect(next_url)


class ChangePassword(View):
    @staticmethod
    def get(request: HttpRequest):
        next_url = request.GET.get('next', '/')

        if not request.user.is_authenticated:
            return redirect(reverse('user_management:login') + f'?next={next_url}')

        form = forms.PasswordChangeForm()
        return TemplateResponse(request,
                                'generic_forms/generic_with_form.html',
                                context=form.form_context(next=next_url))

    @staticmethod
    def post(request: HttpRequest):
        next_url = request.GET.get('next', '/')

        if not request.user.is_authenticated:
            return redirect(resolve_url('user_management:login') + f'?next={next_url}')

        form = forms.PasswordChangeForm(request.POST)

        if not form.is_valid():
            return TemplateResponse(request,
                                    'generic_forms/generic_with_form.html',
                                    context=form.form_context(next=next_url))

        old_pwd = form.cleaned_data['old_password']

        if not request.user.check_password(old_pwd):
            form.add_error('old_password', 'Provide the correct current password')
            return TemplateResponse(request,
                                    'generic_forms/generic_with_form.html',
                                    context=form.form_context(next=next_url))

        if form.cleaned_data['new_password1'] != form.cleaned_data['new_password2']:
            form.add_error('new_password2', 'New password entries must be the same')
            return TemplateResponse(request,
                                    'generic_forms/generic_with_form.html',
                                    context=form.form_context(next=next_url))

        request.user.set_password(form.cleaned_data['new_password1'])
        request.user.save()

        update_session_auth_hash(request, request.user)

        return TemplateResponse(request,
                                'generic_forms/generic_response.html',
                                context={'next': next_url,
                                         'msg': 'Your password has now been changed successfully'})


class ResetPasswordApply(View):
    @staticmethod
    def get(request):
        next_url = request.GET.get('next', '/')
        form = forms.ResetPasswordApplyForm()
        return TemplateResponse(request,
                                'generic_forms/generic_with_form.html',
                                context=form.form_context(next=next_url))

    @staticmethod
    def post(request):
        # Send email to the user with a link to the verification view
        email_template = 'email/password_reset_email.html'
        next_url = request.GET.get('next', '/')

        form = forms.ResetPasswordApplyForm(request.POST)
        if not form.is_valid():
            return TemplateResponse(request,
                                    'generic_forms/generic_with_form.html',
                                    context=form.form_context(next=next_url))

        model: Type[UserExtended | AbstractBaseUser] = get_user_model()

        try:
            user = model.objects.get(email=form.cleaned_data['email'])
        except model.DoesNotExist:
            form.add_error('email', 'This user does not exist')
            return TemplateResponse(request,
                                    'generic_forms/generic_with_form.html',
                                    context=form.form_context(next=next_url))

        if user.is_guest or not user.is_verified:
            error_msg = 'This user is a guest which does not have a password that can be reset' if user.is_guest \
                else 'This user has not completed verification so cannot be reset'
            form.add_error('email', error_msg)
            return TemplateResponse(request,
                                    'generic_forms/generic_with_form.html',
                                    context=form.form_context(next=next_url))

        pwd_reset = PasswordResetApplication.add_password_reset(user=user)

        base_url = request.build_absolute_uri('home')
        url = (request.build_absolute_uri(
            location=reverse("user_management:password_reset_prompt_new", kwargs={"uuid": pwd_reset.uuid})) +
               "?" + escape(f'next={next_url}'))


        html_content = TemplateResponse(request, email_template,
                                        context={'base_url': base_url,
                                                 'url': url}).rendered_content

        site_name = appsettings().get('user_management', {}).get('SITE_NAME', '')
        sender = appsettings().get('user_management', {}).get('EMAIL_SENDER', None)
        sender = sender if sender else settings.EMAIL_HOST_USER

        msg = EmailMultiAlternatives(subject=f'{site_name}: Password reset requested',
                                     from_email=f'{sender}',
                                     to=[user.email])

        msg.attach_alternative(
            f'A password reset for the user using your email address was requested for {site_name}.\n'
                    f'Copy this link : {url} into your browser to complete the password reset.\n\n'
                    f"If you didn't request a reset you can ignore this email.\n",
                               'text/plain')
        msg.attach_alternative(html_content, 'text/html')
        msg.send()

        return TemplateResponse(request, 'generic_forms/generic_response.html',
                                context={'msg': 'A Password reset email has been sent to you. '
                                                'Please check your email and click the button/link.'})


class PasswordResetEnterNew(View):
    """Form to capture new password"""
    @staticmethod
    def get(request, uuid):
        next_url = request.GET.get('next', '/')

        if not PasswordResetApplication.objects.filter(uuid=uuid).exists():
            return HttpResponseServerError(f'Received a password reset with an unknown uuid {uuid}')

        form = forms.PasswordResetForm()
        return TemplateResponse(request,
                                'generic_forms/generic_with_form.html',
                                context=form.form_context(uuid, next=next_url))

    @staticmethod
    def post(request, uuid):
        next_url = request.GET.get('next', '/')

        form = forms.PasswordResetForm(request.POST)
        if not form.is_valid():
            return TemplateResponse(request,
                                    'generic_forms/generic_with_form.html',
                                    context=form.form_context(uuid, next=next_url))

        try:
            application = PasswordResetApplication.objects.get(uuid=uuid)
        except PasswordResetApplication.DoesNotExist:
            return HttpResponseServerError(f'Received a password reset with an unknown uuid {uuid}')

        email = application.email
        try:
            user_model:[UserExtended | AbstractBaseUser] = get_user_model()
            user = user_model.objects.get(email=email)
        except UserExtended.DoesNotExist:
            return HttpResponseServerError('Received a password reset with an unknown email')

        if form.cleaned_data['new_password1'] != form.cleaned_data['new_password2']:
            form.add_error('new_password2', 'The passwords provided must be the same as each other')
            return TemplateResponse(request,
                                    'generic_forms/generic_with_form.html',
                                    context=form.form_context(uuid, next=next_url))

        if user.check_password(form.cleaned_data['new_password1']):
            form.add_error(None, 'Your new password must be different from your current password')
            return TemplateResponse(request,
                                    'generic_forms/generic_with_form.html',
                                    context=form.form_context(uuid, next=next_url))

        user.set_password(form.cleaned_data['new_password1'])
        user.is_verified = True
        user.save()
        update_session_auth_hash(request, request.user)

        application.delete()

        return TemplateResponse(request, 'generic_forms/generic_response.html',
                                context={'msg': 'Your password has now been changed.',
                                         'next': next_url})

class UserProfile(View):
    def get(self, request, team_member_id=None):
        if team_member_id:
            try:
                member_data = TeamMember.objects.get(team_member_id=team_member_id)
            except TeamMember.DoesNotExist:
                return HttpResponseServerError('Team member does not exist')
        else:
            if request.user.has_perm('GarageSale.is_team_member'):
                member_data = TeamMember.objects.get_or_create(user=request.user,
                                                           defaults={'user' : request.user})[0]
            else:
                raise PermissionDenied('You do not have permission to view this page')

        return TemplateResponse(request, 'user_profile/user_profile.html',
                                context={'member_data': member_data})

class UserProfileEdit(UpdateView):
    model = TeamMember
    template_name = 'user_profile/user_profile_edit.html'
    context_object_name = 'member_data'
    fields = ['role', 'picture', 'bio']
    def get(self, request, *args, **kwargs):
        self.object = self.get_object( *args, **kwargs)
        return super().get(request, *args, **kwargs)

    def get_object(self, *args, **kwargs):
        member_id = self.kwargs.get('team_member_id', None)
        try:
            self.object = self.model.objects.get(team_member_id=member_id)
        except self.model.DoesNotExist:
            raise Http404(f"User does not exist, {member_id}")
        return self.object

def id_card_pdf_header(context:dict):
    result = finders.find('user_management/styles/id_card_pdf_header.css')
    if not result:
        return ''
    with open(result) as f:
        template = Template(f.read())
    return template.render(context=Context(context))

def make_pdf( template_file:str, context:dict, header:str, request):
    template_content = get_template(template_file)
    content = template_content.render(context | {'request': request})
    pdf = weasyprint.HTML(io.StringIO(content), base_url=request.build_absolute_uri()).write_pdf(stylesheets=[weasyprint.CSS(string=header)])
    return pdf, content


class TeamMemberIDCard(EntryPointMixin, View):
    entry_point_url = 'user_management:team_member_id_cards'
    entry_point_label = 'Id Cards'
    entry_point_icon = static('user_management/images/icons/id-cards-with-profile-images-variant-svgrepo-com.svg')
    entry_point_permission ='GarageSale.is_manager'
    template_name = 'id_cards/request_id_cards.html'

    def get(self, request):

        return TemplateResponse(request, self.template_name, context={'team_members': TeamMember.objects.all()})

    def post(self, request):
        members = request.POST.getlist('members_chosen')
        instances = TeamMember.objects.filter(id__in=members)

        header = id_card_pdf_header(context={})

        pdf, html = make_pdf(template_file='id_cards/ID_cards.html', context={'member_data': instances,
                                                                     'MEDIA_URL': settings.MEDIA_URL}, header=header, request=request)
        file_name = f'id_cards-{dt.now().strftime("%Y-%m-%d-%H-%M-%S")}.pdf'
       # with open(file_name.replace('pdf','html'), 'w') as f:
       #    f.write(html)
       # return HttpResponse(html, content_type='text/html')

        return HttpResponse(pdf, content_type='application/pdf',
                            headers={"Content-Disposition": f'attachment; filename={file_name}'})

def display_id_card( request, team_member_id=None):
    if team_member_id:
        try:
            member_data = TeamMember.objects.filter(team_member_id=team_member_id)
        except TeamMember.DoesNotExist:
            return HttpResponseServerError('Team member does not exist')
    else:
        member_data = TeamMember.objects.filter()

    return TemplateResponse(request, 'id_cards/ID_cards.html', context={'member_data': member_data})