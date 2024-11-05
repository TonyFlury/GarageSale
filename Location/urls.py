from django.urls import path

from . import views

app_name = 'Location'

urlpatterns = [
    path('create', views.LocationCreateView.as_view(), name= 'create'),
    path('view', views.LocationView.as_view(), name='view'),
]