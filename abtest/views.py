"""A/B test page at /fd986fa (first 7 chars of sha1("noble-shape")).

GET  /fd986fa        show the page; the first GET per visitor counts one impression
POST /fd986fa        the button; counts at most one click per visitor, then
                     redirects back (Post/Redirect/Get), which never counts
                     a second impression or changes the variant
GET  /fd986fa/stats  JSON with `preferred` = variant with the higher click rate
"""

import secrets
import uuid
from fractions import Fraction

from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods

from .models import Click, Impression, Variant

# Course nicknames of the five team members (exactly as shown on 656.mba).
TEAM_NICKNAMES = [
    "poised-ferret",
    "careful-bee",
    "puzzled-reindeer",
    "inquisitive-wombat",
    "encouraging-dove",
]

VARIANTS = [Variant.KUDOS.value, Variant.THANKS.value]
SESSION_VISITOR = "abtest_visitor"
SESSION_VARIANT = "abtest_variant"


def _visitor_and_variant(request):
    """Return (visitor_id, variant), assigning both on a visitor's first request.

    Both live in the session, so reloads and the redirect after a click see the
    same values. They survive log-in too: Django keeps session data when it
    rotates the session key.
    """
    session = request.session
    if not session.get(SESSION_VISITOR):
        session[SESSION_VISITOR] = uuid.uuid4().hex
    if session.get(SESSION_VARIANT) not in VARIANTS:
        session[SESSION_VARIANT] = secrets.choice(VARIANTS)  # 50/50
    return session[SESSION_VISITOR], session[SESSION_VARIANT]


@never_cache
@require_http_methods(["GET", "HEAD", "POST"])
def ab_page(request):
    visitor, variant = _visitor_and_variant(request)

    if request.method == "POST":
        # Only a visitor who was shown the page can click; credit the click to
        # the variant they were shown.
        impression = Impression.objects.filter(visitor=visitor).first()
        if impression is not None:
            Click.objects.get_or_create(
                visitor=visitor, defaults={"variant": impression.variant}
            )
        return redirect("abtest")

    if request.method == "GET":  # HEAD (e.g. uptime pings) never counts
        Impression.objects.get_or_create(visitor=visitor, defaults={"variant": variant})

    return render(
        request,
        "abtest/page.html",
        {
            "variant": variant,
            "nicknames": TEAM_NICKNAMES,
            "clicked": Click.objects.filter(visitor=visitor).exists(),
        },
    )


def _click_rate(clicks, impressions):
    # Exact fractions, so a tie really is a tie (no float rounding).
    return Fraction(clicks, impressions) if impressions else Fraction(0)


@never_cache
@require_GET
def ab_stats(request):
    data = {}
    for v in VARIANTS:
        impressions = Impression.objects.filter(variant=v).count()
        clicks = Click.objects.filter(variant=v).count()
        data[v] = {
            "impressions": impressions,
            "clicks": clicks,
            "click_rate": round(float(_click_rate(clicks, impressions)), 4),
        }

    kudos_rate = _click_rate(data["kudos"]["clicks"], data["kudos"]["impressions"])
    thanks_rate = _click_rate(data["thanks"]["clicks"], data["thanks"]["impressions"])
    # Ties (including no data at all) go to "kudos" so the key is always valid.
    preferred = "thanks" if thanks_rate > kudos_rate else "kudos"

    return JsonResponse({"preferred": preferred, **data})
