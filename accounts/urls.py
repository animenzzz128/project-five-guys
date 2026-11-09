"""Owner: B. Account routes, at the top level like most web apps (/login/, /signup/).

/login without the slash redirects to /login/ (Django's APPEND_SLASH), so the
short form works too. The names "login" / "logout" / "signup" are what
settings.LOGIN_URL and the templates use.
"""

from django.urls import path

from . import views

urlpatterns = [
    path("login/", views.LoginView.as_view(), name="login"),
    path("logout/", views.LogoutView.as_view(), name="logout"),
    path("signup/", views.signup, name="signup"),
]
