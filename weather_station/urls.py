from django.contrib import admin
from django.urls import path, include

from django.views.generic import RedirectView, TemplateView

from datasets import views as datasets_views

# OTPAdminSite is applied in datasets.admin (imported via AppConfig / admin autodiscover).
import datasets.admin  # noqa: F401

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', RedirectView.as_view(pattern_name='dashboard')),
    path(
        'dashboard/',
        datasets_views.dashboard,
        name='dashboard',
        ),
    path(
       'weather_api/',
       include(
           "datasets.api.urls",
           namespace='datasets-api'
           )
       ),
    path(
        "robots.txt",
        TemplateView.as_view(
            template_name="robots.txt",
            content_type="text/plain",
        )
    ),
]
