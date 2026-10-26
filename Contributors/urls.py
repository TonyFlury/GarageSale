from django.urls import path

from .views import general_views, rest_api
from .views.upload import UploadCSV
from .views.download import DownloadCSV
from .views.contact_history import add_contact_history
from .views.details import contributor_details
from .views.contributions import add_contribution, delete_contribution


app_name = "contributors"

urlpatterns = [
    path("spreadsheet/<int:pk>/contributions/<int:contribution_pk>/delete/", delete_contribution, name="delete_contribution"),
    path("upload/", UploadCSV.as_view(), name="upload"),
    path("download/", DownloadCSV.as_view(), name="download"),
    path("spreadsheet/", general_views.ContributorSpreadsheetView.as_view(), name="spreadsheet"),
    path("spreadsheet/create/", rest_api.contributor_spreadsheet_create, name="spreadsheet_create"),
    path("spreadsheet/<int:pk>/save/", rest_api.contributor_spreadsheet_save, name="spreadsheet_save"),
    path("spreadsheet/<int:pk>/contact-history/", add_contact_history, name="contact_history"),
    path("spreadsheet/<int:pk>/details/", contributor_details, name="details"),
    path("spreadsheet/<int:pk>/contributions/", add_contribution, name="add_contribution"),
]
