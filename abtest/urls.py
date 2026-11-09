"""Owner: C. The A/B test page lives at the first 7 chars of sha1("noble-shape")."""

from django.urls import path

from . import views

urlpatterns = [
    path("fd986fa", views.ab_page, name="abtest"),
    path("fd986fa/stats", views.ab_stats, name="abtest_stats"),
]
