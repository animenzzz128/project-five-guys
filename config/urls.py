"""Root URL config. Each app owns its own urls.py; nobody needs to edit this file.

- accounts/urls.py  (B): e.g. /accounts/login/, /accounts/signup/
- abtest/urls.py    (C): /fd986fa and /fd986fa/stats
- ai/urls.py        (C): /colleges/ask/ (one-sentence search)
- core/urls.py      (A/D): / and /healthz
"""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("accounts.urls")),
    path("", include("abtest.urls")),
    path("", include("ai.urls")),
    path("", include("core.urls")),
]
