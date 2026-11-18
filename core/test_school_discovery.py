import csv
import gzip
from collections import Counter

from django.test import SimpleTestCase

from core.management.commands.apply_catalog_links import DATA, read_links


class SchoolDiscoveryTests(SimpleTestCase):
    def test_published_coverage_reconciles_with_scorecard_and_link_snapshots(self):
        snapshot = DATA / "scorecard_2026"
        with gzip.open(snapshot / "institutions.csv.gz", "rt") as stream:
            schools = {int(row["unitid"]) for row in csv.DictReader(stream)}
        with (DATA / "catalog_directories.csv").open() as stream:
            configured = {int(row["unitid"]) for row in csv.DictReader(stream)}
        with (snapshot / "catalog_scan_coverage.csv").open() as stream:
            coverage = list(csv.DictReader(stream))
        self.assertCountEqual([int(row["unitid"]) for row in coverage], schools - configured)
        links = read_links()
        with gzip.open(snapshot / "programs.csv.gz", "rt") as stream:
            fields = {(int(row["unitid"]), row["cip_code"], int(row["credential_level"]))
                      for row in csv.DictReader(stream)}
        self.assertFalse(links.keys() - fields)
        counts = Counter(unit for unit, _, _ in links)
        for row in coverage:
            count = counts[int(row["unitid"])]
            self.assertEqual(int(row["matches"]), count)
            self.assertEqual(row["status"] == "matched", count > 0)
