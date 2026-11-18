from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import redirect_to_login
from django.db import transaction
from django.db.models import OuterRef, Subquery
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .models import Institution, Shortlist, ShortlistItem


def with_saved_item(schools, user):
    if not user.is_authenticated:
        return schools
    items = ShortlistItem.objects.filter(shortlist__user=user, institution=OuterRef("pk")).order_by("pk")
    return schools.annotate(saved_item_id=Subquery(items.values("pk")[:1]))


def return_page(request):
    target = request.POST.get("next", "")
    if target.startswith("/") and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()},
                                                                  require_https=request.is_secure()):
        return target
    return reverse("shortlist")


@login_required
def shortlist(request):
    items = ShortlistItem.objects.filter(shortlist__user=request.user).select_related("institution", "shortlist")
    items = items.order_by("shortlist__name", "position", "added_at", "pk")
    return render(request, "core/shortlist.html", {"items": items})


@require_POST
def add(request, unitid):
    destination = return_page(request)
    if not request.user.is_authenticated:
        return redirect_to_login(destination)
    school = get_object_or_404(Institution, unitid=unitid)
    with transaction.atomic():
        if not ShortlistItem.objects.filter(shortlist__user=request.user, institution=school).exists():
            personal, _ = Shortlist.objects.get_or_create(user=request.user, name="My shortlist")
            ShortlistItem.objects.get_or_create(shortlist=personal, institution=school)
    return redirect(destination)


@require_POST
def remove(request, pk):
    destination = return_page(request)
    if not request.user.is_authenticated:
        return redirect_to_login(destination)
    item = get_object_or_404(ShortlistItem.objects.select_related("institution", "shortlist"),
                             pk=pk, shortlist__user=request.user)
    if request.POST.get("confirm") != "yes":
        return render(request, "core/confirm_remove.html", {"item": item, "next": destination})
    item.delete()
    return redirect(destination)
