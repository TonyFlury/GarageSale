from django.urls import path

from . import views

app_name = "contributors"

urlpatterns = [
    path("spreadsheet/", views.contributor_spreadsheet, name="spreadsheet"),
    path("spreadsheet/create/", views.contributor_spreadsheet_create, name="spreadsheet_create"),
    path("spreadsheet/<int:pk>/save/", views.contributor_spreadsheet_save, name="spreadsheet_save"),
]
