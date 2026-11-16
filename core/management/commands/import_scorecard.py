"""Load the nationwide bachelor's catalog bundled with this release."""
import csv
import gzip
from itertools import batched
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import Institution, Program

DATA = Path(__file__).resolve().parents[2] / "data"
SNAPSHOT = DATA / "scorecard_2026"
SCHOOL_RELEASE = "Scorecard 2026-11-02"
FIELD_RELEASE = "Scorecard 2026-10-15"


def records(filename):
    with gzip.open(SNAPSHOT / filename, "rt", encoding="utf-8", newline="") as source:
        yield from csv.DictReader(source)


def import_institutions():
    count = 0
    for batch in batched(records("institutions.csv.gz"), 500):
        schools = []
        for row in batch:
            for field, value in row.items():
                if value == "" and Institution._meta.get_field(field).null:
                    row[field] = None
            schools.append(Institution(**row, data_release=SCHOOL_RELEASE))
        Institution.objects.bulk_create(
            schools, update_conflicts=True, unique_fields=["unitid"],
            update_fields=[key for key in batch[0] if key != "unitid"] + ["data_release", "updated_at"],
        )
        count += len(schools)
    return count


def import_fields(school_ids):
    count = 0
    for batch in batched(records("programs.csv.gz"), 500):
        programs = []
        for row in batch:
            unitid = int(row["unitid"])
            if unitid not in school_ids:
                raise CommandError(f"Field of Study has unmatched UNITID {unitid}")
            programs.append(Program(
                institution_id=school_ids[unitid], cip_code=row["cip_code"], name=row["name"],
                credential_level=int(row["credential_level"]), degree="Bachelor's degree", data_release=FIELD_RELEASE,
            ))
        Program.objects.bulk_create(
            programs, update_conflicts=True, unique_fields=["institution", "cip_code", "credential_level"],
            update_fields=["name", "degree", "data_release"],
        )
        count += len(programs)
    return count


class Command(BaseCommand):
    help = "Load the complete pinned U.S. bachelor's snapshot and the separately verified degree links."

    @transaction.atomic
    def handle(self, *args, **options):
        institutions = import_institutions()
        school_ids = dict(Institution.objects.filter(data_release=SCHOOL_RELEASE).values_list("unitid", "pk"))
        fields = import_fields(school_ids)
        call_command("import_programs", str(DATA / "cs_programs.csv"), stdout=self.stdout)
        self.stdout.write(f"Imported {institutions} institutions and {fields} federal fields of study.")
