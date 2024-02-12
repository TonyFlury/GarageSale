#!/usr/bin/env python
# coding=utf-8

import django.forms as forms
from django.forms import Field
from django.contrib.auth.models import User


class Registration(forms.ModelForm):

    next = forms.CharField(widget=forms.HiddenInput())
    email_template = forms.CharField(widget=forms.HiddenInput())
    redirect = forms.CharField(widget=forms.HiddenInput())

    class Meta:
        model = User
        fields = ['email', 'first_name', 'last_name','password']
        widgets = {'password': forms.PasswordInput(),
                   'email': forms.EmailInput(attrs={'size': 40, 'required': 'True'}),
                   'first_name': forms.TextInput(attrs={'size': 40, 'required': 'True'}),
                   'last_name': forms.TextInput(attrs={'size': 40, 'required': 'True'}),
                   }


class LoginForm(forms.ModelForm):
    email = forms.EmailInput(attrs={'size': 40, 'required': 'True'})
    password = forms.PasswordInput()

    class Meta:
        model = User
        fields = ['email', 'password']
        widgets = {'password': forms.PasswordInput(),
                   'email': forms.EmailInput(attrs={'size': 40, 'required': 'True'}),}
