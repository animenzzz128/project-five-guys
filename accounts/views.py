from urllib.parse import urlsplit

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth import views as auth_views
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

from core.models import ShortlistItem

from .forms import EmailAuthenticationForm, SignupForm
from .models import ApplicantType, Profile

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


# ---------- Dashboard: where signed-in users land ----------

# One line under the greeting, by the "I am a…" choice made at sign-up.
DASHBOARD_LEDES = {
    ApplicantType.HIGH_SCHOOL: "Let's find colleges that fit who you are and what you can afford.",
    ApplicantType.COLLEGE: "Transferring or heading to grad school? Let's find programs that fit.",
    ApplicantType.PROFESSIONAL: "Grad school, an MBA, or something new: let's find programs that fit your plans.",
    ApplicantType.SUPPORTER: "Helping someone apply? Build and check the shortlist together.",
}
DEFAULT_LEDE = "Here's where your college search stands, and what to do next."


def _journey(school_count):
    """The five steps of the product, each marked done from the user's own data.

    `ready` is False while a step's page has not been built yet; the template
    then says "Coming soon" instead of linking to a page that does not exist.
    """
    steps = [
        {"key": "priorities", "title": "Set your priorities", "text": "Budget, region, size and major.", "done": False},
        {"key": "search", "title": "Search colleges", "text": "Start from what matters, not a name.", "done": school_count > 0},
        {"key": "shortlist", "title": "Build your shortlist", "text": "Save the schools worth a closer look.", "done": school_count > 0},
        {"key": "compare", "title": "Compare side by side", "text": "Cost, outcomes and selectivity in one table.", "done": False},
        {"key": "ask", "title": "Ask the AI", "text": "Questions about your list, with sources.", "done": False},
    ]
    next_step = next((step for step in steps if not step["done"]), None)
    for step in steps:
        step["ready"] = False
        step["is_next"] = step is next_step
    return steps


@login_required
def dashboard(request):
    user = request.user
    profile = Profile.for_user(user)
    items = ShortlistItem.objects.filter(shortlist__user=user)
    school_count = items.values("institution").distinct().count()
    steps = _journey(school_count)
    done = sum(step["done"] for step in steps)
    email = user.email or user.get_username()

    return render(
        request,
        "accounts/dashboard.html",
        {
            "display_name": email.split("@")[0],
            "profile": profile,
            "lede": DASHBOARD_LEDES.get(profile.applicant_type, DEFAULT_LEDE) if profile else DEFAULT_LEDE,
            "steps": steps,
            "steps_done": done,
            "progress": round(done / len(steps), 2),
            "school_count": school_count,
            "shortlist_count": user.shortlists.count(),
            "recent_items": items.select_related("institution", "shortlist").order_by(
                "-shortlist__updated_at", "position", "added_at"
            )[:4],
        },
    )
