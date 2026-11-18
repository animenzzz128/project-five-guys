from django.urls import path

from . import views

urlpatterns = [
    path("colleges/ask/", views.ask, name="ai_search"),
]
