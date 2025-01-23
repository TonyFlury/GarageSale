from django.urls import path
from django.conf import settings
from django.views.generic import TemplateView

from . import views

app_name = 'What3Words_mapping'

urlpatterns = [
    path('', views.MapView.as_view(), name='index'),
    path('<str:widget>/', views.MapView.as_view(), name='map'),
]
