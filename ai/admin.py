from django.contrib import admin

from .models import SearchInterpretation


@admin.register(SearchInterpretation)
class SearchInterpretationAdmin(admin.ModelAdmin):
    list_display = ("text", "user", "created_at")
    search_fields = ("text", "user__username", "user__email")
    readonly_fields = ("user", "text", "raw_json", "params", "notes", "created_at")
