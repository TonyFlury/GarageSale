import datetime

from django import forms
from django.contrib.admin.widgets import AdminDateWidget
from django.urls import reverse_lazy

from GarageSale.models import EventData, MOTD
from News.models import NewsArticle


class BaseEventForm(forms.ModelForm):
    class Meta:
        model = EventData
        fields = '__all__'

    def clean(self):
        """ Validate the various date fields against each other - does this need to be so complex
        """
        cleaned_data = super().clean()
        event_date = cleaned_data['event_date']

        if event_date <= datetime.date.today():
            self.add_error('event_date', 'Event Date must be later than today')
        open_billboard = cleaned_data['open_billboard_bookings']
        close_billboard = cleaned_data['close_billboard_bookings']

        if open_billboard <= datetime.date.today():
            self.add_error('open_billboard_bookings',
                           'The date for opening billboard bookings must be later than today')
        if open_billboard >= event_date:
            self.add_error('open_billboard_bookings',
                           'The date for opening billboard bookings must be earlier than the event date')

        if close_billboard <= datetime.date.today():
            self.add_error('close_billboard_bookings',
                           'The date for closing billboard bookings must be later than today')
        if close_billboard <= open_billboard:
            self.add_error('close_billboard_bookings', 'The date for closing must be later '
                                                       'than the date for opening Billboard bookings')
        if close_billboard >= event_date:
            self.add_error('close_billboard_bookings',
                           'The date for closing billboard bookings must be earlier than the event date')

        open_sales_bookings = cleaned_data['open_sales_bookings']
        if open_sales_bookings <= datetime.date.today():
            self.add_error('open_sales_bookings', 'The date for opening billboard bookings must be later than today')
        if open_sales_bookings >= event_date:
            self.add_error('open_sales_bookings',
                           'The date for opening billboard bookings must be earlier than the event date')

        close_sales_bookings = cleaned_data['close_sales_bookings']
        if close_sales_bookings <= datetime.date.today():
            self.add_error('close_sales_bookings', 'The date for closing billboard bookings must be later than today')
        if close_sales_bookings <= open_sales_bookings:
            self.add_error('close_sales_bookings',
                           'The date for closing must be later than the date for Opening Sales bookings date')
        if close_sales_bookings >= event_date:
            self.add_error('close_sales_bookings',
                           'The date for closing billboard bookings must be earlier than the event date')

        use_from = cleaned_data['use_from']
        if use_from >= event_date:
            self.add_error('use_from', f'The Use From date must be earlier than the date of the event')


class AddContextMixin:
    """Mixin class to save repeating 'get_context_data'
    """
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        components = self.request.path.strip('/').split('/')
        data_type = components[1] if len(components) > 1 else None
        action = components[-1] if len(components) > 1 else None

        extra = self.kwargs | ({'data_type': data_type} if data_type else {}) | ({'action': action} if action else {})

        return context | extra


class EventObjectMixin:
    """Mixin class to save repeating 'get_object'
    """
    def get_object(self, queryset=None):
        return EventData.objects.get(event_date=self.kwargs['event_date'])


class NewsObjectMixin:
    """Mixin class to save repeating 'get_object'
    """
    def get_object(self, queryset=None):
        return NewsArticle.objects.get(id=self.kwargs['news_id'])


class MOTDObjectMixin:

    def get_object(self, queryset=None):
        return MOTD.objects.get(pk=self.kwargs['motd_id'])


class GetNewsFormMixin:
    def get_form(self, form=None):
        """Add the Admin Date Widget to all date fields - by name for now"""
        form = super().get_form(form)
        form.fields['publish_by'].widget = AdminDateWidget(attrs={'type': 'date'})
        form.fields['publish_by'].default = datetime.date.today() + datetime.timedelta(1)
        form.fields['publish_by'].input_formts = ['%d %m %Y']
        form.fields['expire_by'].widget = AdminDateWidget(attrs={'type': 'date'})
        form.fields['expire_by'].default = datetime.date.today() + datetime.timedelta(1)
        form.fields['expire_by'].input_formts = ['%d %m %Y']
        return form

    def get_success_url(self):
        """Return the URL to be used when the Event is created successfully """
        fragments = [key for key, item in self.request.GET.items() if item=='']

        return reverse_lazy('TeamPagesNews') + ('?'+ '&'.join(fragments)) if fragments else ''

class GetMotdFormMixin:
    def get_form(self, form=None):
        """Add the Admin Date Widget to all date fields - by name for now"""
        form = super().get_form(form)
        form.fields['use_from'].widget = AdminDateWidget(attrs={'type': 'date'})
        form.fields['use_from'].default = datetime.date.today() + datetime.timedelta(1)
        form.fields['use_from'].input_formts = ['%d %m %Y']
        return form

    def get_success_url(self):
        """Return the URL to be used when the Event is created successfully """
        return reverse_lazy('TeamPagesRoot')


class GetEventFormMixin:
    """Mixin class to save repeating 'get_form'
    """
    def get_form(self, form=None):
        """Add the Admin Date Widget to all date fields - by name for now"""
        form = super().get_form(form)
        for field in ['event_date',
                      'open_billboard_bookings', 'close_billboard_bookings', 'open_sales_bookings',
                      'close_sales_bookings',
                      'use_from']:
            form.fields[field].widget = AdminDateWidget(attrs={'type': 'date'})
            form.fields[field].default = datetime.date.today() + datetime.timedelta(1)
            form.fields[field].input_formts = ['%d %m %Y']

        return form

    def get_success_url():
        """Return the URL to be used when the Event is created successfully """
        return reverse_lazy('TeamPagesRoot')


