import csv

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import Institution, Program


class Command(BaseCommand):
    help = "Import a normalized UTF-8 program CSV for existing schools, matched by federal UNITID."

    def add_arguments(self, parser):
        parser.add_argument("csv_path")

    @transaction.atomic
    def handle(self, *args, csv_path, **options):
        required = {"unitid", "name", "degree", "catalog_url"}
        optional = {"cip_code", "summary", "core_courses", "entry_requirements", "capstone", "catalog_year"}
        schools = dict(Institution.objects.exclude(data_release=Institution.SAMPLE).values_list("unitid", "pk"))
        seen = set()
        created = 0
        with open(csv_path, encoding="utf-8-sig", newline="") as source:
            reader = csv.DictReader(source)
            headers = reader.fieldnames or []
            if not required.issubset(headers) or set(headers) - required - optional or len(set(headers)) != len(headers):
                raise CommandError("Expected unitid, name, degree, catalog_url and supported Program columns.")
            for row in reader:
                if None in row or None in row.values():
                    raise CommandError(f"Line {reader.line_num}: column count mismatch.")
                values = {key: value.strip() for key, value in row.items()}
                unitid = values.pop("unitid")
                if not unitid.isascii() or not unitid.isdecimal() or int(unitid) not in schools:
                    raise CommandError(f"Line {reader.line_num}: unknown institution UNITID {unitid!r}.")
                key = (schools[int(unitid)], values.pop("name"), values.pop("degree"))
                if key in seen:
                    raise CommandError(f"Line {reader.line_num}: duplicate program in input.")
                seen.add(key)
                program, new = Program.objects.get_or_create(
                    institution_id=key[0], name=key[1], degree=key[2], credential_level=None, defaults=values
                )
                for field, value in values.items():
                    setattr(program, field, value)
                try:
                    program.full_clean()
                except ValidationError as error:
                    raise CommandError(f"Line {reader.line_num}: {error}") from error
                program.save()
                created += int(new)
        self.stdout.write(f"Processed {len(seen)} programs; created {created}.")
