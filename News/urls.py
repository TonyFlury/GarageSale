#!/usr/bin/env python
# coding=utf-8
"""
    GarageSale.urls.py : 

Summary :
    
    
Use Case :
    
    
Testable Statements :
    ...0
"""
from .views import Article, news_page,news_letter_subscribe

from django.urls import path

app_name = "News"

urlpatterns = [
    path("", news_page, name="NewsPage"),
    path("article/<slug:slug>", Article.as_view(), name="article"),
    path("subscribe", news_letter_subscribe, name='subscribe'),
]
