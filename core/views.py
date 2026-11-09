import logging

from django.db import connection
from django.http import JsonResponse
from django.shortcuts import render

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
