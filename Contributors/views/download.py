import csv

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.views import View

from django.core.exceptions import PermissionDenied
from GarageSale.access_policy import contributor_types
from Contributors.models import Contributor
from Contributors.views.upload import UploadCSV


class DownloadCSV(LoginRequiredMixin, View):
    """Export all contributors using the upload's standard model fields."""

    def get(self, request, *args, **kwargs):
        """Render the initial page or download using the configured standard fields."""
        kinds = contributor_types(request.user, "export")
        selected = request.GET.get("contributor_type")
        if selected:
            kinds = [kind for kind in kinds if kind == selected]
        if not kinds:
            raise PermissionDenied("You do not have permission to export these contributors.")
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="contributors.csv"'
        writer = csv.writer(response)
        fields = UploadCSV.CSV_FIELD_NAMES
        writer.writerow(fields)
        rows = Contributor.objects.filter(contributor_type__in=kinds).order_by("contributor_name", "pk").values_list(*fields)
        writer.writerows(rows.iterator())
        return response
