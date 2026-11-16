"""Apply the reviewed catalog snapshot without performing network requests at deploy time."""

import csv
from pathlib import Path
from urllib.parse import urlsplit

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from core.models import Program

DATA = Path(__file__).resolve().parents[2] / "data"


def read_links():
    with (DATA / "catalog_directories.csv").open() as stream:
        directories = {int(row["unitid"]): row for row in csv.DictReader(stream)}
    links = {}
    with (DATA / "scorecard_2026/catalog_links.csv").open() as stream:
        for row in csv.DictReader(stream):
            key = (int(row["unitid"]), row["cip_code"], int(row["credential_level"]))
            url = row["catalog_url"]
            parsed = urlsplit(url)
            source = directories.get(key[0])
            if (key in links or key[2] != 3 or not source or parsed.scheme != "https"
                    or parsed.netloc != urlsplit(source["index_url"]).netloc
                    or not parsed.path.startswith(source["path_prefix"]) or len(url) > 600):
                raise CommandError(f"Invalid or duplicate official catalog match for {key}")
            links[key] = url
    if not links:
        raise CommandError("Empty link snapshot")
    return links


class Command(BaseCommand):
    help = "Apply exact school/field catalog matches, preserving independently edited URLs."

    @transaction.atomic
    def handle(self, *args, **options):
        links = read_links()
        units = {key[0] for key in links}
        rows = (Program.objects.select_related("institution").select_for_update()
                .filter(credential_level=3)
                .filter(Q(institution__unitid__in=units) | ~Q(last_collected_url="")))
        changed = []
        for program in rows:
            key = (program.institution.unitid, program.cip_code, program.credential_level)
            target = links.pop(key, "")
            if program.catalog_url != program.last_collected_url:
                # An editor supplied or cleared this link; keep the editor's decision.
                continue
            if target != program.catalog_url:
                program.catalog_url = program.last_collected_url = target
                changed.append(program)
        if links:
            raise CommandError(f"Missing {len(links)} federal program rows; run import_scorecard first.")
        Program.objects.bulk_update(changed, ["catalog_url", "last_collected_url"], batch_size=250)
        self.stdout.write(f"Updated {len(changed)} official program links.")
