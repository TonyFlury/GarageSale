from django.template.response import TemplateResponse
from django.views.generic import TemplateView
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


class MapView(TemplateView):
    template_name = 'forms/widgets/testytest.html'

    def render_to_response(self, context, **response_kwargs):
        if context.get('widget') == 'w3w':
            return TemplateResponse(request=self.request, template='forms/widgets/What3WordsMap.html', context=context)
        else:
            return TemplateResponse(request=self.request, template='forms/widgets/testytest.html', context=context)

    def get_context_data(self, **kwargs):
        context = super(MapView, self).get_context_data(**kwargs)
        kwargs.setdefault('widget', 'location')

        try:
            context["WHAT3WORDS_API_KEY"] = settings.WHAT3WORDS_API_KEY
        except AttributeError:
            raise ImproperlyConfigured("Need to define WHAT3WORDS_API_KEY setting.")
        try:
            context["GOOGLE_MAP_API_KEY"] = settings.GOOGLE_MAP_API_KEY
        except AttributeError:
                raise ImproperlyConfigured("Need to define GOOGLE_KEY setting.")
        return context
