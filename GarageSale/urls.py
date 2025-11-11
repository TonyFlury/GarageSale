"""
URL configuration for GarageSale project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include, reverse_lazy
from django.conf import settings
from django.conf.urls.static import static
from .views import general_views

from django.views.generic import TemplateView
from django.views.generic.base import RedirectView

urlpatterns = [
    path('admin/', admin.site.urls),
    path("", general_views.home, name="home"),
    path("newhome", TemplateView.as_view(template_name='home.html'), name="NewHome"),
    path("getInvolved", RedirectView.as_view(url=reverse_lazy('Location:view'))),
#    path("getInvolved", include('Location.urls'), name="getInvolved"),
    path('about_us', TemplateView.as_view(template_name='aboutUs.html'), name='AboutUs'),
    path('contact', TemplateView.as_view(template_name='contact.html'), name='ContactUs'),
    path('privacy', TemplateView.as_view(template_name='privacy_policy.html'), name='Privacy'),
    path('blind_auction', TemplateView.as_view(template_name='blind_auction.html'), name='BlindAuction'),
    path('donate', TemplateView.as_view(template_name='donate.html'), name='Donate'),
    path('location/', include('Location.urls')),
    path('team_page/', include('team_pages.urls')),
    path('news/', include('News.urls')),
    path('user/', include('user_management.urls')),
#    path('billboard/', include('Billboard.urls')),
#    path('sale_location/', include('SaleLocation.urls')),

    # path('test/<int:case>/', views.testing, name='test'),
    path('sponsors/', include('Sponsors.urls')),
    path('CraftMarket/', include('CraftMarket.urls')),
    path('mapping/', include('DjangoGoogleMap.urls')),
    path('summernote/', include('django_summernote.urls')),
]


if settings.DEBUG:
    urlpatterns += path("__debug__/", include("debug_toolbar.urls")),
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
