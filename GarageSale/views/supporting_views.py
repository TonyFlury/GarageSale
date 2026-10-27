"""Management pages for the charities supported by events."""
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.views import View
from django.templatetags.static import static
from django.urls import reverse
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from GarageSale.models import Supporting
from TeamPageFramework.entry_point import register
from team_pages.forms import SupportingForm


register("Supported charities", "TeamPages:SupportingList",
         static("GarageSale/images/icons/supported-charities.svg"),
         permission="GarageSale.view_supporting", needs_event=False, nav_page="Finance and funding", order=30)


class SupportingList(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = Supporting
    permission_required = "GarageSale.view_supporting"
    template_name = "supporting/list.html"
    context_object_name = "organisations"
    ordering = ("index", "pk")


class SupportingDetail(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = Supporting
    permission_required = "GarageSale.view_supporting"
    template_name = "supporting/detail.html"


class SupportingSearch(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "GarageSale.view_supporting"

    def get(self, request):
        organisations = Supporting.objects.order_by("name", "pk")
        query = request.GET.get("q", "").strip()
        if query:
            organisations = organisations.filter(name__icontains=query)
        selected = [pk for pk in request.GET.getlist("selected") if pk.isdecimal()]
        organisations = organisations.exclude(pk__in=selected)
        page = Paginator(organisations, 20).get_page(request.GET.get("page", 1))
        return JsonResponse({
            "results": [{"id": item.pk, "name": item.name} for item in page],
            "page": page.number, "pages": page.paginator.num_pages,
            "count": page.paginator.count,
        })


class SupportingFormMixin(LoginRequiredMixin, PermissionRequiredMixin):
    model = Supporting
    form_class = SupportingForm
    template_name = "supporting/form.html"

    def get_success_url(self):
        return reverse("TeamPages:SupportingDetail", args=[self.object.pk])


class SupportingCreate(SupportingFormMixin, CreateView):
    permission_required = "GarageSale.add_supporting"

    def form_valid(self, form):
        form.instance.index = 100
        return super().form_valid(form)


class SupportingEdit(SupportingFormMixin, UpdateView):
    permission_required = "GarageSale.change_supporting"
