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
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from . import views

from django.views.generic import TemplateView

urlpatterns = [
    path('admin/', admin.site.urls),
    path("", views.home, name="home"),
    path("getInvolved", TemplateView.as_view(template_name="getInvolved.html"), name="getInvolved"),
    path('about_us', TemplateView.as_view(template_name='aboutUs.html'), name='AboutUs'),
    path('contact', TemplateView.as_view(template_name='contact.html'), name='ContactUs'),
    path("__debug__/", include("debug_toolbar.urls")),
    path('news/', include('News.urls')),
    path('user/', include('user_management.urls')),
    path('billboard/', include('Billboard.urls')),
    path('sale_location/', include('SaleLocation.urls')),
    path('sponsors/', include('Sponsors.urls')),

]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)