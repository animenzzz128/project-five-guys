"""A/B test data: one Impression and at most one Click per visitor.

A "visitor" is a random id stored in the Django session the first time
someone opens /fd986fa. The unique constraint on `visitor` makes the
database itself enforce "count once per visitor", even if two requests
from the same browser arrive at the same moment.
"""

from django.db import models


class Variant(models.TextChoices):
    KUDOS = "kudos", "kudos"
    THANKS = "thanks", "thanks"


class Impression(models.Model):
    visitor = models.CharField(max_length=32, unique=True)
    variant = models.CharField(max_length=6, choices=Variant.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["variant"])]

    def __str__(self):
        return f"{self.variant} impression @ {self.created_at:%Y-%m-%d %H:%M}"


class Click(models.Model):
    visitor = models.CharField(max_length=32, unique=True)
    variant = models.CharField(max_length=6, choices=Variant.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["variant"])]

    def __str__(self):
        return f"{self.variant} click @ {self.created_at:%Y-%m-%d %H:%M}"
