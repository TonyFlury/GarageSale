import datetime

from django import forms
from django_summernote.widgets import SummernoteWidget

from GarageSale.models import EventData, MOTD, Supporting
from django.db import transaction
from Sponsors.models import Sponsor
from News.models import NewsArticle


class OrderedSupportingWidget(forms.CheckboxSelectMultiple):
    template_name = "event/supporting_widget.html"

    def get_context(self, name, value, attrs):
        from django.urls import reverse
        context = super().get_context(name, value, attrs)
        context["widget"]["search_url"] = reverse("TeamPages:SupportingSearch")
        return context


class OrderedSupportingField(forms.ModelMultipleChoiceField):
    def clean(self, value):
        organisations = super().clean(value)
        by_id = {str(item.pk): item for item in organisations}
        return [by_id[pk] for pk in dict.fromkeys(map(str, value or []))]


class SupportingForm(forms.ModelForm):
    class Meta:
        model = Supporting
        fields = ["name", "website", "logo"]


class EventForm(forms.ModelForm):
    supporting_organisations = OrderedSupportingField(
        queryset=Supporting.objects.order_by("index", "pk"), required=False,
        widget=OrderedSupportingWidget,
        help_text="Search and add charities, then set the order of the selected charities. "
                  "This order is shared by all events supporting these charities.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["event_logo"].required = False
        # Show selected organisations first, preserving their current order.
        selected = self["supporting_organisations"].value() or []
        selected_ids = [str(getattr(item, "pk", item)) for item in selected]
        # Only selected records belong in the page; the directory is searched in pages.
        valid_ids = [pk for pk in selected_ids if pk.isdecimal()]
        organisations = list(self.fields["supporting_organisations"].queryset.filter(pk__in=valid_ids))
        positions = {pk: i for i, pk in enumerate(selected_ids)}
        organisations.sort(key=lambda item: positions.get(str(item.pk), len(positions)))
        self.fields["supporting_organisations"].choices = [(item.pk, item.name) for item in organisations]

    def _save_m2m(self):
        super()._save_m2m()
        for index, organisation in enumerate(self.cleaned_data["supporting_organisations"], start=1):
            Supporting.objects.filter(pk=organisation.pk).update(index=index)

    @transaction.atomic
    def save(self, commit=True):
        return super().save(commit=commit)

    class Meta:
        model = EventData
        fields = '__all__'
        widgets = {"event_logo": forms.ClearableFileInput(), **{
            name: forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"})
            for name in ("event_date", "open_billboard_bookings", "close_billboard_bookings",
                         "open_sales_bookings", "close_sales_bookings", "use_from")
        }}


class SponsorForm(forms.ModelForm):
    class Meta:
        model = Sponsor
        exclude =['event']
        widgets = {'gift': forms.Textarea(attrs={'cols':50,'rows':2}),
                   'description': forms.Textarea(attrs={'cols':50,'rows':4}),
                }


class MotdForm(forms.ModelForm):
    class Meta:
        model = MOTD
        fields = '__all__'
        widgets = {
        'html_content': SummernoteWidget(attrs={'summernote': {'width': '100%', 'height': '300px'}}), }

class NewsForm(forms.ModelForm):
    class Meta:
        model = NewsArticle
        fields = '__all__'
        widgets = {'publish_by': forms.DateInput(attrs={'type': 'date'}),
                   'expire_by': forms.DateInput(attrs={'type': 'date'}),
                   'synopsis': forms.Textarea(attrs={'cols':45,'rows':4})}
        exclude = ['slug', 'published']

    def clean(self):
        cleaned_data = super().clean()

        if cleaned_data['front_page'] and not cleaned_data['synopsis']:
            self.add_error('synopsis', 'A synopsis must be provided for articles intended for the front-page')
