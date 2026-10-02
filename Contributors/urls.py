from django.urls import path

from .views import general_views, rest_api


app_name = "contributors"

urlpatterns = [
    path("spreadsheet/", general_views.contributor_spreadsheet, name="spreadsheet"),
    path("spreadsheet/create/", rest_api.contributor_spreadsheet_create, name="spreadsheet_create"),
    path("spreadsheet/<int:pk>/save/", rest_api.contributor_spreadsheet_save, name="spreadsheet_save"),
]
