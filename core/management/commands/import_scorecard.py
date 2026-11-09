"""Bulk-import real College Scorecard rows.  Owner: D.

Deliberately NOT run by `build.sh`: a human runs it on purpose, and the rows
it writes carry a real `data_release` label so the interface can tell them
apart from seeded demo data.

Sprint 1 ships the command shape only; Sprint 2 fills in `_fetch` and turns
this into the "importing external data" technical-challenge item.

    python manage.py import_scorecard --release 2024-25
"""

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Import institutions from the federal College Scorecard API."

    def add_arguments(self, parser):
        parser.add_argument("--release", required=True, help='Release label, e.g. "2024-25".')
        parser.add_argument("--limit", type=int, default=None, help="Stop after N rows (for testing).")

    def handle(self, *args, **options):
        raise CommandError(
            "Not implemented yet (Sprint 2). Use `python manage.py seed` for demo data."
        )
