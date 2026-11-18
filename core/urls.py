from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("programs/", views.programs, name="programs"),
    path("healthz", views.healthz, name="healthz"),
]
