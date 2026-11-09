"""Seed the database with grader accounts and demo data.  Owner: D.

`build.sh` runs this on every Render deploy, so it MUST be safe to run any
number of times.  Everything below uses get_or_create / update_or_create and
never `create`, so a second run changes nothing.

Grader passwords come from the environment, never from this file: the repo is
public, and seed re-sets the password on every deploy, so a committed password
could not be changed from the admin either.  Set SEED_ADMIN_PASSWORD and
SEED_STUDENT_PASSWORD in the Render dashboard; the real values go in the
assignment's submission notes, not in git.

It deliberately makes no network calls: a deploy must not fail because an
external API is slow, and the course requires that tests never touch real
external services.  Real College Scorecard rows come from a separate command,
`import_scorecard`, which a human runs on purpose.

    python manage.py seed
"""

import json
import os
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import Institution, Shortlist, ShortlistItem

SAMPLE_DATA = Path(__file__).resolve().parent.parent.parent / "data" / "sample_institutions.json"

# Grader accounts.  Fake addresses, no 2FA, and passwords supplied by the
# environment.  `dev_password` is used ONLY when DEBUG is on, so it can never
# reach staging or production (render.yaml sets DEBUG=False there).
GRADER_ACCOUNTS = [
    {
        "username": "admin",
        "email": "admin@example.com",
        "password_env": "SEED_ADMIN_PASSWORD",
        "dev_password": "dev-only-admin-not-for-deployment",
        "is_staff": True,
        "is_superuser": True,
    },
    {
        "username": "student",
        "email": "student@example.com",
        "password_env": "SEED_STUDENT_PASSWORD",
        "dev_password": "dev-only-student-not-for-deployment",
        "is_staff": False,
        "is_superuser": False,
    },
]

DEMO_SHORTLIST_NAME = "Fall 2027 applications"
DEMO_SHORTLIST_PICKS = [
    (900001, "In-state tuition, strong retention. Safety."),
    (900003, "Best earnings outcome on the list. Target."),
    (900010, "Reach. Need to check aid before applying."),
]


def resolve_password(spec):
    """Grader password for one account: environment first, dev fallback only on DEBUG."""
    value = os.environ.get(spec["password_env"], "").strip()
    if value:
        return value, "environment"
    if settings.DEBUG:
        return spec["dev_password"], "local dev default"
    raise CommandError(
        f"{spec['password_env']} is not set. Grader passwords must come from the "
        "environment when DEBUG is off. Set it in the Render dashboard (see "
        ".env.example and DEPLOY.md); never commit it."
    )


class Command(BaseCommand):
    help = "Create grader accounts and demo data. Safe to run repeatedly."

    @transaction.atomic
    def handle(self, *args, **options):
        users = self._seed_users()
        created, updated = self._seed_institutions()
        self._seed_demo_shortlist(users["student"])

        self.stdout.write(
            self.style.SUCCESS(
                f"Seed complete: {len(users)} accounts, "
                f"{created} institutions created, {updated} updated."
            )
        )
        self.stdout.write(
            "Sample institutions are stored with data_release='SAMPLE'. "
            "Run `python manage.py import_scorecard` for real federal data."
        )

    def _seed_users(self):
        User = get_user_model()
        users = {}
        for spec in GRADER_ACCOUNTS:
            password, source = resolve_password(spec)
            user, created = User.objects.get_or_create(
                username=spec["username"],
                defaults={
                    "email": spec["email"],
                    "is_staff": spec["is_staff"],
                    "is_superuser": spec["is_superuser"],
                },
            )
            # Re-apply on every run so a changed flag is restored and the
            # account still works after a database reset.
            user.email = spec["email"]
            user.is_staff = spec["is_staff"]
            user.is_superuser = spec["is_superuser"]
            user.set_password(password)
            user.save()
            users[spec["username"]] = user
            # Never log the password itself, only where it came from.
            self.stdout.write(
                f"  {'created' if created else 'updated'} user {user.username} "
                f"(password from {source})"
            )
        return users

    def _seed_institutions(self):
        payload = json.loads(SAMPLE_DATA.read_text(encoding="utf-8"))
        created = updated = 0
        for row in payload["institutions"]:
            fields = {k: v for k, v in row.items() if k != "unitid"}
            fields["data_release"] = Institution.SAMPLE
            _, was_created = Institution.objects.update_or_create(
                unitid=row["unitid"], defaults=fields
            )
            created += was_created
            updated += not was_created
        return created, updated

    def _seed_demo_shortlist(self, student):
        shortlist, _ = Shortlist.objects.get_or_create(
            user=student, name=DEMO_SHORTLIST_NAME
        )
        for position, (unitid, note) in enumerate(DEMO_SHORTLIST_PICKS):
            institution = Institution.objects.filter(unitid=unitid).first()
            if institution is None:
                continue
            ShortlistItem.objects.update_or_create(
                shortlist=shortlist,
                institution=institution,
                defaults={"note": note, "position": position},
            )
