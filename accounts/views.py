from urllib.parse import urlsplit

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth import views as auth_views
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

from .forms import EmailAuthenticationForm, SignupForm

AUTH_PAGE_NAMES = ("login", "logout", "signup")


def _is_auth_page(url):
    return urlsplit(url).path in {reverse(name) for name in AUTH_PAGE_NAMES}


def _safe_next(request):
    """The ?next= target if it is on this site and not an account page, else the default landing page.

    Account pages are excluded so a signed-in visitor can never be bounced
    between /login/ and /signup/ in a loop.
    """
    target = request.POST.get("next") or request.GET.get("next") or ""
    allowed = url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    )
    if allowed and not _is_auth_page(target):
        return target
    return settings.LOGIN_REDIRECT_URL


def signup(request):
    if request.user.is_authenticated:
        return redirect(_safe_next(request))

    form = SignupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, "Welcome to Admit Compass. Your account is ready.")
        return redirect(_safe_next(request))

    next_url = request.POST.get("next") or request.GET.get("next") or ""
    return render(request, "registration/signup.html", {"form": form, "next": next_url})


class LoginView(auth_views.LoginView):
    authentication_form = EmailAuthenticationForm
    redirect_authenticated_user = True

    def get_redirect_url(self):
        # Same rules as sign-up: on-site only, never back to an account page.
        # (Django's own check would raise a 500 on /login/?next=/login/.)
        url = super().get_redirect_url()
        return "" if url and _is_auth_page(url) else url

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "You're logged in.")
        return response


class LogoutView(auth_views.LogoutView):
    """POST only (Django 5): a GET returns 405, so a link or image can't log people out."""

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        messages.info(request, "You're logged out.")
        return response
