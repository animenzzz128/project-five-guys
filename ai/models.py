from django.conf import settings
from django.db import models


class SearchInterpretation(models.Model):
    """How one sentence typed into the AI search was understood (#38).  Owner: C.

    `raw_json` is the validated LLM reply; `params` the `/colleges/` query it
    produced after server-side checks; `notes` the wishes that did not become
    filters. Each row belongs to one user and is never shown to anyone else.
    """

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="search_interpretations")
    text = models.CharField(max_length=300)
    raw_json = models.JSONField()
    params = models.JSONField(default=dict)
    notes = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.user}: {self.text[:60]}"
