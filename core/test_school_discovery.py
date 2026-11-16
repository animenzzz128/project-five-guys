import csv
import gzip
from collections import Counter
from unittest.mock import AsyncMock

from django.test import SimpleTestCase
from lxml import html

from core.management.commands.apply_catalog_links import DATA, read_links
from scripts.scan_school_catalogs import campus_specific, eligible_url, scan


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

    def test_public_official_links_and_campus_scope(self):
        home = "https://north.example.edu/"
        peers = [home, "https://south.example.edu/"]
        self.assertIsNone(eligible_url(home, "https://example.edu.other.org/biology", home))
        self.assertIsNone(eligible_url(home, "https://user@example.edu/biology", home))
        self.assertTrue(campus_specific("https://north.example.edu/biology", home, peers))
        self.assertFalse(campus_specific("https://south.example.edu/biology", home, peers))
        self.assertFalse(campus_specific(home, home, [home, home]))

    async def test_follows_index_and_requires_undergraduate_evidence(self):
        home = "https://example.edu/"
        pages = {
            home: '<a href="/degrees/">Programs</a>',
            home + "degrees/": '<h1>Undergraduate programs</h1><a href="/programs/physics/">Physics</a>'
                               '<a href="/programs/history-ba/">History, BA</a>'
                               '<a href="/programs/history-bs/">History, BS</a>'
                               '<a href="/programs/astronomy/">Astronomy</a>'
                               '<a href="https://vendor.net/math/">Mathematics</a>',
            home + "programs/physics/": '<h1>Physics</h1>',
        }
        async def fetch(url, _home):
            if url == home + "programs/astronomy/":
                return home + "graduate/programs/astronomy/", html.fromstring("<h1>Astronomy</h1>")
            return url, html.fromstring(pages[url])

        web = AsyncMock()
        web.page.side_effect = fetch
        fields = [{"name": n, "cip_code": c} for n, c in
                  [("Physics.", "4008"), ("History.", "5401"), ("Mathematics.", "2701"), ("Astronomy.", "4002")]]
        result = await scan({"unitid": "42", "school_url": home}, fields, web, {})
        self.assertEqual(result["matches"], [["4008", home + "programs/physics/", home + "degrees/"]])

    async def test_department_title_only_cannot_establish_degree(self):
        home = "https://example.edu/"
        page = html.fromstring('<a href="/programs/chemistry/">Chemistry</a>')
        detail = html.fromstring('<h1>Chemistry</h1><footer><h2>Bachelor of Science</h2></footer>')
        web = AsyncMock()
        web.page.side_effect = [(home, page), (home + "programs/chemistry/", detail)]
        result = await scan({"unitid": "42", "school_url": home}, [{"name": "Chemistry.", "cip_code": "4005"}],
                            web, {}, extended=True)
        self.assertEqual(result["matches"], [])
