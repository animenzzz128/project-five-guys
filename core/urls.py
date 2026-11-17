from django.urls import path

from . import colleges, shortlists, views

urlpatterns = [
    path("", views.home, name="home"),
    path("healthz", views.healthz, name="healthz"),
    path("colleges/", colleges.colleges, name="colleges"),
    path("colleges/<int:unitid>/", colleges.college_detail, name="college_detail"),
    path("shortlist/", shortlists.shortlist, name="shortlist"),
    path("shortlist/add/<int:unitid>/", shortlists.add, name="shortlist_add"),
    path("shortlist/remove/<int:pk>/", shortlists.remove, name="shortlist_remove"),
]
