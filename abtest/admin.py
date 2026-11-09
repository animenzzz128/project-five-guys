"""Registered so test visits can be reviewed and deleted before the graded A/B run."""

from django.contrib import admin

from .models import Click, Impression


@admin.register(Impression, Click)
class ABEventAdmin(admin.ModelAdmin):
    list_display = ("variant", "visitor", "created_at")
    list_filter = ("variant",)
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
