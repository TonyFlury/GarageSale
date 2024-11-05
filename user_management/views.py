import datetime
from uuid import uuid1

from django.utils import timezone
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login as login_user
from django.http import HttpResponseServerError, HttpRequest
from django.core.mail import send_mail
from django.core.mail import EmailMultiAlternatives
from django.shortcuts import redirect, reverse
from django.template.response import TemplateResponse
from django.utils.html import escape
from django.db import transaction
from django.shortcuts import resolve_url
from django.views.generic import View
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.contrib.auth import authenticate

from . import forms
from . import models

from .apps import appsettings, settings
from django.contrib.auth import get_user_model, login, logout, update_session_auth_hash


# ToDo - show password Help on registration, and validate password format
# ToDo - test password Reset stuff
# ToDo - Remove old templates - retest first

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
    msg.attach_alternative(f'Your one time code is {short_code} - '
                           f'please enter this value into the website',
                           'text/plain')
    msg.attach_alternative(html_content, 'text/html')
    msg.send()


def guest_error(incoming_request, short_code_entry=None):
    next = incoming_request.GET['next']

    try:
        code_inst = models.GuestVerifier.objects.get(pk=short_code_entry)
    except models.GuestVerifier.DoesNotExist:
        raise SystemError('Invalid Short Code on error page !')

    match code_inst.reason_code:
        case 'expired':
            pre_form = 'Your existing short code expired'
        case 'entry_error':
            pre_form = 'You failed to enter the correct short code after 3 attempts.'
        case _:
            pre_form = ''

    form = forms.GuestApplicationError()

    return TemplateResponse(incoming_request,
                            'generic_with_form.html',
                            context=form.form_context(
                                action_path=resolve_url('user_management:resend', short_code_entry=short_code_entry),
                                pre_form=pre_form,
                                next=next))


def resend_short_code(incoming_request, short_code_entry=None):
    """"Simple view to resend a new short-code - use existing short_code
        as the original data for the next
    """
    email_template = "email/guest_short_code-email.html"

    redirect_url = incoming_request.GET.get('next', '/')
    try:
        inst: models.GuestVerifier = models.GuestVerifier.objects.get(short_code=short_code_entry)
    except models.GuestVerifier.DoesNotExist:
        raise ObjectDoesNotExist('Original short_code does not exist')

    email = inst.email
    models.GuestVerifier.remove_expired(email=email)
    send_guest_verification_email(email=email, short_code=inst, template=email_template)

    new_inst = models.GuestVerifier.add_guest_verifier(email=email)

    return redirect(reverse('user_management:input_short_code',
                            kwargs={'short_code_entry': new_inst.pk}) + f'?next={redirect_url}')


class GuestApplication(View):
    email_template = "email/guest_short_code-email.html"

    def get(self, incoming_request):
        redirect_url = incoming_request.GET.get('next', '/')

        form = forms.GuestRequestForm()
        return TemplateResponse(incoming_request,
                                template='generic_with_form.html',
                                context=form.form_context(next=redirect_url))

    def post(self, incoming_request: HttpRequest):
        next = incoming_request.GET.get('next', '/')

        form = forms.GuestRequestForm(incoming_request.POST)
        if not form.is_valid():
            return TemplateResponse(incoming_request,
                                    'generic_with_form.html',
                                    context=form.form_context(next=next)
                                    )

        email = form.cleaned_data['email']

        # We know the data is a valid email - remove old entries and add a new entry
        models.GuestVerifier.remove_expired(email=email)
        code = models.GuestVerifier.add_guest_verifier(email=email)

        send_guest_verification_email(incoming_request,
                                      email=form.cleaned_data['email'],
                                      short_code=code,
                                      template=self.email_template)

        return redirect(resolve_url('user_management:input_short_code', short_code_entry=code.pk) + f'?next={next}')


class InputShortCode(View):

    @staticmethod
    def _obfuscate_email(short_code_inst: models.GuestVerifier) -> str:
        email = short_code_inst.email
        tld = email.split('.')[-1]
        name, domain = email.split('@')[0], email.split('@')[1]
        return name[0:4].rjust(len(name), '*') + '@' + domain[0:4].rjust(len(domain), '*') + '.' + tld

    def get(self, incoming_request, short_code_entry):
        next = incoming_request.GET.get('next', '/')
        try:
            code_inst = models.GuestVerifier.objects.get(pk=short_code_entry)
        except models.UserVerification.DoesNotExist:
            raise ObjectDoesNotExist(f'Received Invalid ShortCode pk {short_code_entry} ')

        form = forms.InputShortCodeForm(data={'email': code_inst.email})

        return TemplateResponse(request=incoming_request,
                                template='ShortCodeInput.html',
                                context={'form': form,
                                         'email': code_inst.email,
                                         'action': resolve_url('user_management:input_short_code',
                                                               short_code_entry=short_code_entry) + f'?next={next}',
                                         'resend_url': resolve_url('user_management:resend',
                                                                   short_code_entry=short_code_entry) + f'?next={next}',
                                         'obfuscated_email': self._obfuscate_email(code_inst)})

    def post(self, incoming_request: HttpRequest, short_code_entry):
        next = incoming_request.GET.get('next', '/')

        try:
            code_inst = models.GuestVerifier.objects.get(pk=short_code_entry)
        except models.GuestVerifier.DoesNotExist:
            raise ObjectDoesNotExist(f'No such GuestVerifierObject : {short_code_entry}')

        form = forms.InputShortCodeForm(data=incoming_request.POST)
        if not form.is_valid():
            return TemplateResponse(request=incoming_request,
                                    template='ShortCodeInput.html',
                                    context={'form': form,
                                             'action': resolve_url('user_management:input_short_code',
                                                                   short_code_entry=short_code_entry) + f'?next={next}',
                                             'obfuscated_email': self._obfuscate_email(code_inst)})

        if form.cleaned_data['email'] != code_inst.email:
            raise ValidationError(f'email address for guest request don\'t match')

        # The data matched - ie the form is valid - check for expiry
        if code_inst.is_time_expired():
            code_inst.reason_code = 'expired'
            code_inst.save()
            return redirect(resolve_url('user_management:guest_error', short_code_entry=code_inst.pk)+f'?next={next}')

        if form.cleaned_data['short_code'] != code_inst.short_code:
            code_inst.retry_count -= 1
            code_inst.save()

            # Only re-show the form if the retry count hasn't hit zero
            if code_inst.retry_count > 0:
                # Build a blank form

                form = forms.InputShortCodeForm(data={'email': code_inst.email})
                form.add_error(None, 'Short code Incorrect - please try again')

                return TemplateResponse(request=incoming_request,
                                        template='ShortCodeInput.html',
                                        context={'form': form,
                                                 'action': resolve_url('user_management:input_short_code',
                                                                       short_code_entry=short_code_entry) + f'?next={next}',
                                                 'obfuscated_email': self._obfuscate_email(code_inst),
                                                 'retry_count': code_inst.retry_count,
                                                 'max_retry': code_inst.max_retry}, )
            else:
                code_inst.reason_code = 'entry_error'
                code_inst.save()
                return redirect( resolve_url('user_management:guest_error', short_code_entry=code_inst.pk)
                                 + f'?next={next}' )

        # The code is correct and no expired - redirect to the 'next' url
        # Create a guest user if necessary
        try:
            user_inst = get_user_model().objects.get(email=code_inst.email)
        except get_user_model().DoesNotExist:
            user_inst = None

        # Create a guest user account if necessary - allow a two hour time out on guest users
        if user_inst:
            login(request=incoming_request, user=user_inst)
            incoming_request.session.set_expiry(timezone.now()+datetime.timedelta(hours=2))
        else:
            user = get_user_model().objects.create_guest_user(email=code_inst.email)
            login(request=incoming_request, user=user)
            incoming_request.session.set_expiry(timezone.now()+datetime.timedelta(hours=2))

        return redirect(next)


def identify(incoming_request: HttpRequest):
    """Render a simple login, login as Guest button sets"""
    next_url = incoming_request.GET.get('next', '/')
    return TemplateResponse(incoming_request, template='identify.html',
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
    def get(incoming_request):
        redirect_url = incoming_request.GET.get('redirect', '/')

        form = forms.RegistrationForm()
        return TemplateResponse(incoming_request,
                                'generic_with_form.html',
                                context=form.form_context(redirect_url=redirect_url))

    def post(self, incoming_request):

        redirect_url = incoming_request.GET.get('redirect', '/')

        # Build a form instance for validation purposes.
        form = forms.RegistrationForm(incoming_request.POST)

        if not form.is_valid():
            return TemplateResponse(incoming_request,
                                    'generic_with_form.html',
                                    context=form.form_context(redirect_url=redirect_url))
        if form.is_valid():
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

                verify = models.UserVerification(email=form.cleaned_data['email'], uuid=secret)
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

    try:
        verify = models.UserVerification.objects.get(uuid=uuid)
    except models.UserVerification.DoesNotExist:
        return TemplateResponse(request, template='generic_response.html',
                                context={'redirect': redirect_url,
                                         'msg': """
                                         This verification link has already been used, and the user account is ready to be used"""})

    # TODO - add timeout logic
    user = User.objects.get(email=verify.email)
    user.is_active = True
    user.save()
    verify.delete()

    return redirect(redirect_url)


class Login(View):
    @staticmethod
    def get(request):
        """Render a new blank form"""

        next = redirect_url = request.GET.get('next', '/')
        form = forms.LoginForm()

        return TemplateResponse(request,
                                'generic_with_form.html',
                                context=form.form_context(
                                    reset_path='user_management:reset_password_application',
                                    next=next))

    @staticmethod
    def post(request):
        """deal with the submitted form"""
        redirect_url = request.GET.get('redirect', '/')
        form_inst = forms.LoginForm(request.POST)
        if not form_inst.is_valid():
            return TemplateResponse(request,
                                    'generic_with_form.html',
                                    context=form_inst.form_context(next=redirect_url))

        try:
            user_inst = get_user_model().objects.get(email=form_inst.cleaned_data['email'])
        except get_user_model().DoesNotExist:
            form_inst.add_error(None, "Invalid User/password combination")
            return TemplateResponse(request,
                                    'generic_with_form.html',
                                    context=form_inst.form_context(next=redirect_url))

        # Sign this user in
        user = authenticate(username=form_inst.cleaned_data['email'],
                            password=form_inst.cleaned_data['password'])

        if user is None:
            form_inst.add_error(None, 'Invalid User/password combination')
            return TemplateResponse(request,
                                    'generic_with_form.html',
                                    context=form_inst.form_context(next=redirect_url))
        else:
            login_user(request, user)
            return redirect(redirect_url)


class ChangePassword(View):
    @staticmethod
    def get(request: HttpRequest):
        redirect_url = request.GET.get('redirect', '/')

        if not request.user.is_authenticated:
            return redirect(resolve_url('user_management:login') + f'?redirect={redirect_url}')

        form = forms.PasswordChangeForm()
        return TemplateResponse(request,
                                'generic_with_form.html',
                                context=form.form_context(next=redirect_url))

    @staticmethod
    def post(request: HttpRequest):
        redirect_url = request.GET.get('redirect', '/')

        if not request.user.is_authenticated:
            return redirect(resolve_url('user_management:login') + f'?redirect={redirect_url}')

        form = forms.PasswordChangeForm(request.POST)

        if not form.is_valid():
            return TemplateResponse(request,
                                    'generic_with_form.html',
                                    context=form.form_context(next=redirect_url))

        old_pwd = form.cleaned_data['old_password']

        if not request.user.check_password(old_pwd):
            form.add_error('old_password', 'Provide the correct current password')
            return TemplateResponse(request,
                                    'generic_with_form.html',
                                    context=form.form_context(next=redirect_url))

        if form.cleaned_data['new_password1'] != form.cleaned_data['new_password2']:
            form.add_error('new_password2', 'New password entries must be the same')
            return TemplateResponse(request,
                                    'generic_with_form.html',
                                    context=form.form_context(next=redirect_url))

        request.user.set_password(form.cleaned_data['new_password1'])
        request.user.save()

        update_session_auth_hash(request, request.user)

        return TemplateResponse(request,
                                'generic_response.html',
                                context={'redirect': redirect_url,
                                         'msg': 'Your password has now been changed successfully'})


class ResetPasswordApply(View):
    @staticmethod
    def get(request):
        redirect_url = request.GET.get('redirect', '/')
        form = forms.ResetPasswordApplyForm()
        return TemplateResponse(request,
                                'generic_with_form.html',
                                context=form.form_context(next=redirect_url))

    @staticmethod
    def post(request):
        # Send email to the user with a link to the verification view
        email_template = 'email/password_reset_email.html'
        redirect_url = request.GET.get('redirect', '/')

        form = forms.ResetPasswordApplyForm(request.POST)
        if not form.is_valid():
            return TemplateResponse(request,
                                    'generic_with_form.html',
                                    context=form.form_context(next=redirect_url))

        try:
            user = User.objects.get(username=form.cleaned_data['email'])
        except User.DoesNotExist:
            form.add_error('email', 'No user exists with this email address')
            return TemplateResponse(request,
                                    'generic_with_form.html',
                                    context=form.form_context(next=redirect_url))

        base_url = request.build_absolute_uri('home')
        secret = uuid1()
        url = (request.build_absolute_uri(
            location=reverse("user_management:reset_password", kwargs={"uuid": secret})) +
               "?" + escape(f'redirect={redirect_url}'))

        pwd_reset = models.PasswordResetApplication(user=user,
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
    @staticmethod
    def get(request, uuid):
        redirect_url = request.GET.get('redirect', '/')

        if not models.PasswordResetApplication.objects.filter(uuid=uuid).exists():
            return HttpResponseServerError(f'Received a password reset with an unknown uuid {uuid}')

        form = forms.PasswordResetForm()
        return TemplateResponse(request,
                                'generic_with_form.html',
                                context=form.form_context(uuid, next=redirect_url))

    @staticmethod
    def post(request, uuid):
        redirect_url = request.GET.get('redirect', '/')

        form = forms.PasswordResetForm(request.POST)
        if not form.is_valid():
            return TemplateResponse(request,
                                    'generic_with_form.html',
                                    context=form.form_context(uuid, next=redirect_url))

        try:
            application = models.PasswordResetApplication.objects.get(uuid=uuid)
        except models.PasswordResetApplication.DoesNotExist:
            return HttpResponseServerError(f'Received a password reset with an unknown uuid {uuid}')

        user: User = application.user

        if form.cleaned_data['new_password1'] != form.cleaned_data['new_password2']:
            form.add_error('new_password2', 'The passwords provided must be the same as each other')
            return TemplateResponse(request,
                                    'generic_with_form.html',
                                    context=form.form_context(uuid, next=redirect_url))

        if user.check_password(form.cleaned_data['new_password1']):
            form.add_error(None, 'Your new password must be different from your current password')
            return TemplateResponse(request,
                                    'generic_with_form.html',
                                    context=form.form_context(uuid, next=redirect_url))

        user.set_password(form.cleaned_data['new_password1'])
        user.save()
        update_session_auth_hash(request, request.user)

        application.delete()

        return TemplateResponse(request, 'generic_response.html',
                                context={'msg': 'Your password has now been changed.',
                                         'redirect': redirect_url})
