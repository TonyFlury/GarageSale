"""Management pages for the charities supported by events."""
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.templatetags.static import static
from django.urls import reverse
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from GarageSale.models import Supporting
from TeamPageFramework.entry_point import register
from team_pages.forms import SupportingForm


register("Supported charities", "TeamPages:SupportingList",
         static("GarageSale/images/icons/navigation/calendar-date-event-svgrepo-com.svg"),
         permission="GarageSale.view_supporting", needs_event=False)


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
