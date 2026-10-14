import csv

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.views import View

from Contributors.models import Contributor
from Contributors.views.upload import UploadCSV


class DownloadCSV(LoginRequiredMixin, View):
    """Export all contributors using the upload's standard model fields."""

    def get(self, request, *args, **kwargs):
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="contributors.csv"'
        writer = csv.writer(response)
        fields = UploadCSV.CSV_FIELD_NAMES
        writer.writerow(fields)
        rows = Contributor.objects.order_by("contributor_name", "pk").values_list(*fields)
        writer.writerows(rows.iterator())
        return response
