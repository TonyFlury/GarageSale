#!/usr/bin/env python
# coding=utf-8

from django_quill.forms import QuillFormField
from django.forms import ModelForm
from .models import NewsArticle


class NewsArticle(ModelForm):
    class Meta:
        model = NewsArticle
        content = QuillFormField()
        fields = ['headline', 'content', 'publish_by', 'expire_by', 'front_page']