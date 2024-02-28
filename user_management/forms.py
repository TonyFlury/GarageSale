#!/usr/bin/env python
# coding=utf-8

import django.forms as forms
from django.forms import Field
from django.contrib.auth.models import User
from django.shortcuts import render, resolve_url
from django.utils.html import escape


class RegistrationForm(forms.Form):
    email = forms.EmailField(label='Your email')
    first_name = forms.CharField(max_length=256, label='First Name')
    last_name = forms.CharField(max_length=256, label='Last/Surname Name')
    password = forms.CharField(widget=forms.PasswordInput, label='Password')
    password_repeat = forms.CharField(widget=forms.PasswordInput, label='Password (repeat)')

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

    def form_context(self, action_path='', register_path='', reset_path='', redirect_url=''):
        """Return the context needed for this form in the generic template"""
        action_url = resolve_url(action_path) if action_path else resolve_url('user_management:login')
        reset_url = resolve_url(reset_path) if reset_path else resolve_url('user_management:reset_password_application')
        register_url = resolve_url(register_path) if register_path \
            else resolve_url('user_management:reset_password_application')
        redirect_url = escape(redirect_url) if redirect_url else resolve_url('home')

        return {'form_title': 'Login',
                'action': action_url + f'?redirect={redirect_url}',
                'method': 'POST',
                'form': self,
                'post_form': f'Problems logging in - do you need to '
                             f'<a href=\"{reset_url}?redirect={redirect_url}\">Password reset</a> ?',
                'buttons': [
                    {'name': 'Cancel', 'type': 'button', 'redirect': redirect_url},
                    {'name': 'Login', 'type': 'submit'},
                    {'name': 'Register User', 'type': 'button', 'redirect': register_url + f'?redirect={redirect_url}'}]}


class PasswordChangeForm(forms.Form):
    old_password = forms.CharField(widget=forms.PasswordInput, label='Current Password')
    new_password1 = forms.CharField(widget=forms.PasswordInput, label='New Password')
    new_password2 = forms.CharField(widget=forms.PasswordInput, label='New Password (repeat)')

    def form_context(self, action_path='', reset_password_path='', redirect_url=''):
        """Return the context needed for this form in the generic template"""
        action_url = resolve_url(action_path) if action_path \
            else resolve_url('user_management:change_password')
        reset_password_url = resolve_url(reset_password_path) if reset_password_path \
            else resolve_url('user_management:reset_password_application')
        redirect_url = escape(redirect_url) if redirect_url else resolve_url('home')

        return {'form_title': 'Password Change',
                'action': action_url + f'?redirect={redirect_url}',
                'method': 'POST',
                'form': self,
                'post_form': f'Problems logging in - do you need to '
                             f'<a href=\"{reset_password_url}?redirect={redirect_url}\">Password reset</a> ?',
                'buttons': [
                    {'name': 'Cancel', 'type': 'button', 'redirect': redirect_url},
                    {'name': 'Change Password', 'type': 'submit'} ]}


class ResetPasswordApplyForm(forms.Form):
    email = forms.EmailField()

    def form_context(self, action_path='', reset_password_path='', redirect_url=''):
        """Return the context needed for this form in the generic template"""
        action_url = resolve_url(action_path) if action_path \
            else resolve_url('user_management:reset_password_application')
        redirect_url = escape(redirect_url) if redirect_url else resolve_url('home')

        return {'form_title': 'Password Reset Application',
                'action': action_url + f'?redirect={redirect_url}',
                'method': 'POST',
                'form': self,
                'buttons': [
                    {'name': 'Reset Form', 'type':'reset'},
                    {'name': 'Cancel', 'type': 'button', 'redirect': redirect_url},
                    {'name': 'Request Password Reset', 'type': 'submit'} ]}


class PasswordResetForm(forms.Form):
    new_password1 = forms.CharField(widget=forms.PasswordInput, label='New password')
    new_password2 = forms.CharField(widget=forms.PasswordInput, label='New password (repeat)')

    def form_context(self, uuid, action_path='', redirect_url=''):
        """Return the context needed for this form in the generic template"""
        action_url = resolve_url(action_path, uuid) if action_path \
            else resolve_url('user_management:reset_password', uuid)
        redirect_url = escape(redirect_url) if redirect_url else resolve_url('home')

        return {'form_title': 'Reset my Password',
                'action': action_url + f'?redirect={redirect_url}',
                'method': 'POST',
                'form': self,
                'buttons': [
                    {'name': 'Reset Form', 'type': 'reset'},
                    {'name': 'Password Reset', 'type': 'submit'}]}
