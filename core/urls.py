from django.urls import path

from . import colleges, views

urlpatterns = [
    path("", views.home, name="home"),
    path("healthz", views.healthz, name="healthz"),
    path("colleges/", colleges.colleges, name="colleges"),
    path("colleges/<int:unitid>/", colleges.college_detail, name="college_detail"),
]
