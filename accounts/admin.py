from django.contrib import admin

from .models import Profile


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "applicant_type", "created_at")
    list_filter = ("applicant_type",)
    search_fields = ("user__email", "user__username")
    raw_id_fields = ("user",)
