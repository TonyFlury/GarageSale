from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from Contributors.models import Contributor


@login_required
def contributor_spreadsheet(request):
    contributors = Contributor.objects.all().order_by("contributor_name")

    return render(
        request,
        "contributor_spreadsheet.html",
        {
            "contributors": contributors,
        },
    )
