import logging

from django.core.paginator import Paginator
from django.db import connection
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render

from .models import Program

logger = logging.getLogger(__name__)


def home(request):
    # Landing page. The template extends templates/base.html; its layout is B's.
    return render(request, "core/home.html")


def healthz(request):
    """Liveness + database check, used by Render's health check."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        logger.exception("Health check failed: database unreachable")
        return JsonResponse({"status": "error", "database": "unreachable"}, status=503)
    return JsonResponse({"status": "ok", "database": connection.vendor})


def programs(request):
    """Browse school-specific degree records and federal fields of study."""
    query = request.GET.get("q", "").replace("\x00", "").strip()
    results = Program.objects.select_related("institution")
    if query:
        results = results.filter(Q(institution__name__icontains=query) | Q(name__icontains=query))
    results = results.order_by("institution__name", "name", "degree", "pk")
    page = Paginator(results, 40).get_page(request.GET.get("page"))
    return render(request, "core/programs.html", {"page": page, "query": query})
