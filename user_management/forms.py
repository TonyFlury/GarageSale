#!/usr/bin/env python
# coding=utf-8

from django.core import exceptions
import django.forms as forms
from django.forms import Field
from django.contrib.auth.models import User
from django.shortcuts import render, resolve_url
from django.utils.html import escape
import re

phone_regex = re.compile(r'^('
                         r'0[0-9]{10}$)|                        # Match 01206298272'
                         r'(0[0-9]{4}\ [0-9]{6})|               # Match 01206 298272'
                         r'(0[0-9]{4}\ [0-9]{3}\ [0-9]{3})      # Match 01206 298 272'
                         r')$',
                         flags=re.VERBOSE)


def validate_phone_number(value):
    """Raise an exception if the phone number isn't valid in some form"""
    if not phone_regex.match(value):
        raise exceptions.ValidationError(f'{value} is not a valid phone number')


class InputShortCodeForm(forms.Form):
    email = forms.CharField(widget=forms.HiddenInput())
    short_code = forms.CharField(widget=forms.TextInput(attrs={'size': 7,
                                                               'min_length': 7,
                                                               'max_length': 7,
                                                               'autocomplete': 'one-time-code'}))


# TODO - refactor the forms that use the generic templates - a mixin class that extracts data from class variables
# TODO - Benefit of refector - views don't need to keep repeating the template names etc

class RegistrationForm(forms.Form):
    email = forms.EmailField(label='Your email')
    first_name = forms.CharField(max_length=256, label='First Name')
    last_name = forms.CharField(max_length=256, label='Last/Surname Name')
    password = forms.CharField(widget=forms.PasswordInput, label='Password')
    password_repeat = forms.CharField(widget=forms.PasswordInput, label='Password (repeat)')
    phone = forms.CharField(max_length=12, validators=[validate_phone_number], initial='')
    mobile = forms.CharField(max_length=12, validators=[validate_phone_number], initial='')

    def form_context(self, action_path='', login_path='', redirect_url=''):
        """Return the context needed for this form in the generic template"""
        action_url = resolve_url(action_path) if action_path \
            else resolve_url('user_management:register')
        redirect_url = escape(redirect_url) if redirect_url else resolve_url('home')
        login_url = resolve_url(login_path) if login_path \
            else resolve_url('user_management:login')
        return {'form_title': 'Register new user',
                'action': action_url + f'?redirect={redirect_url}',
                'method': 'POST',
                'form': self,
                'post-form': 'By registering with us you will be able to manage all of your involvement with the'
                             'Garage Sale in one place, whether that is signing up for the Newsletter, requesting'
                             'an advertising board or having your sale included on our map.<br/>'
                             'All of your data is managed in accordance with our privacy policy.',
                'buttons': [
                    {'name': 'Reset Form', 'type': 'reset'},
                    {'name': 'Cancel', 'type': 'button', 'redirect': redirect_url},
                    {'name': 'Login', 'type': 'button', 'redirect': login_url},
                    {'name': 'Register', 'type': 'submit'}]}


class LoginForm(forms.Form):
    email = forms.EmailField(max_length=40, required=True, label='Email')
    password = forms.CharField(widget=forms.PasswordInput, label='Password')

    def form_context(self, action_path='', register_path='', reset_path='', next=''):
        """Return the context needed for this form in the generic template"""
        action_url = resolve_url(action_path) if action_path else resolve_url('user_management:login')
        reset_url = resolve_url(reset_path) if reset_path else resolve_url('user_management:reset_password_application')
        register_url = resolve_url(register_path) if register_path \
            else resolve_url('user_management:reset_password_application')
        next = escape(next) if next else resolve_url('home')

        return {'form_title': 'Login',
                'action': action_url + f'?next={next}',
                'method': 'POST',
                'form': self,
                'post_form': f'Problems logging in - do you need to '
                             f'<a href=\"{reset_url}?next={next}\">Password reset</a> ?',
                'buttons': [
                    {'name': 'Cancel', 'type': 'button', 'redirect': next},
                    {'name': 'Login', 'type': 'submit'},
                    {'name': 'Register User', 'type': 'button', 'next': register_url + f'?redirect={next}'}]}


class PasswordChangeForm(forms.Form):
    old_password = forms.CharField(widget=forms.PasswordInput, label='Current Password')
    new_password1 = forms.CharField(widget=forms.PasswordInput, label='New Password')
    new_password2 = forms.CharField(widget=forms.PasswordInput, label='New Password (repeat)')

    def form_context(self, action_path='', reset_password_path='', next=''):
        """Return the context needed for this form in the generic template"""
        action_url = resolve_url(action_path) if action_path \
            else resolve_url('user_management:change_password')
        reset_password_url = resolve_url(reset_password_path) if reset_password_path \
            else resolve_url('user_management:reset_password_application')
        next = escape(next) if next else resolve_url('home')

        return {'form_title': 'Password Change',
                'action': action_url + f'?next={next}',
                'method': 'POST',
                'form': self,
                'post_form': f'Problems logging in - do you need to '
                             f'<a href=\"{reset_password_url}?next={next}\">Password reset</a> ?',
                'buttons': [
                    {'name': 'Cancel', 'type': 'button', 'next': next},
                    {'name': 'Change Password', 'type': 'submit'}]}


class ResetPasswordApplyForm(forms.Form):
    email = forms.EmailField()

    def form_context(self, action_path='', reset_password_path='', next=''):
        """Return the context needed for this form in the generic template"""
        action_url = resolve_url(action_path) if action_path \
            else resolve_url('user_management:reset_password_application')
        next = escape(next) if next else resolve_url('home')

        return {'form_title': 'Password Reset Application',
                'action': action_url + f'?next={next}',
                'method': 'POST',
                'form': self,
                'buttons': [
                    {'name': 'Reset Form', 'type': 'reset'},
                    {'name': 'Cancel', 'type': 'button', 'next': next},
                    {'name': 'Request Password Reset', 'type': 'submit'}]}


class PasswordResetForm(forms.Form):
    new_password1 = forms.CharField(widget=forms.PasswordInput, label='New password')
    new_password2 = forms.CharField(widget=forms.PasswordInput, label='New password (repeat)')

    def form_context(self, uuid, action_path='', next=''):
        """Return the context needed for this form in the generic template"""
        action_url = resolve_url(action_path, uuid) if action_path \
            else resolve_url('user_management:reset_password', uuid)
        next = escape(next) if next else resolve_url('home')

        return {'form_title': 'Reset my Password',
                'action': action_url + f'?next={next}',
                'method': 'POST',
                'form': self,
                'buttons': [
                    {'name': 'Reset Form', 'type': 'reset'},
                    {'name': 'Password Reset', 'type': 'submit'}]}


class GuestRequestForm(forms.Form):
    email = forms.EmailField()

    def form_context(self, action_path='', next=''):
        action_url = resolve_url(action_path) if action_path \
            else resolve_url('user_management:guest_application')
        return {'form_title': 'Guest Login',
                'action': action_url + f'?next={next}',
                'method': 'POST',
                'form': self,
                'buttons': [
                    {'name': 'Guest Login', 'type': 'submit'}]}


class GuestApplicationError(forms.Form):
    email = forms.EmailField(widget=forms.HiddenInput())

    def form_context(self, action_path, next='', pre_form=''):
        action_url = resolve_url(action_path) if action_path \
            else resolve_url('user_management:guest_application')
        return {'form_title': 'Guest Application - Short Code Input Error',
                'action': action_url + f'?next={next}',
                'pre_form': pre_form,
                'method': 'POST',
                'form': self,
                'buttons': [
                    {'name': 'Send a new Code', 'type': 'submit'}]}
