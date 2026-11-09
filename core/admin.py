from django.contrib import admin

from .models import Institution, Shortlist, ShortlistItem


@admin.register(Institution)
class InstitutionAdmin(admin.ModelAdmin):
    list_display = ("name", "state", "ownership", "admission_rate", "median_earnings_10yr", "data_release")
    list_filter = ("data_release", "ownership", "predominant_degree", "state")
    search_fields = ("name", "city", "unitid")
    ordering = ("name",)


class ShortlistItemInline(admin.TabularInline):
    model = ShortlistItem
    extra = 0
    autocomplete_fields = ("institution",)


@admin.register(Shortlist)
class ShortlistAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "updated_at")
    search_fields = ("name", "user__username")
    inlines = (ShortlistItemInline,)
