"""Recompute the "Find similar" vectors (#16).  Owner: B.

`seed` and `import_scorecard` already call this; run it by hand only after
editing institution data some other way.

    python manage.py build_similarity
"""

from django.core.management.base import BaseCommand

from core.similarity import build_profiles


class Command(BaseCommand):
    help = "Recompute every institution's similarity vector. Safe to run repeatedly."

    def handle(self, *args, **options):
        count = build_profiles()
        self.stdout.write(f"Built similarity profiles for {count} institutions.")
