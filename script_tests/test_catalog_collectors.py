"""Offline collector tests; run with python -m unittest discover -s script_tests."""

from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, patch

from bs4 import BeautifulSoup
from lxml import html

from scripts.collect_program_links import collect
from scripts.scan_school_catalogs import campus_specific, eligible_url, scan


class CollectorTests(TestCase):
    def test_unique_bachelor_only_and_target_title_must_match(self):
        source = {"index_url": "https://example.edu/programs/", "unitid": "42", "path_prefix": "/degrees/",
                  "selector": "a[href]", "format": "degree"}
        index = BeautifulSoup("""
            <a href="/degrees/anth/">Anthropology, BA</a><a href="/degrees/anth/index.html">Anthropology, BA</a>
            <a href="/degrees/chem-ms/">Chemistry, MS</a><a href="https://elsewhere.edu/degrees/chem/">Chemistry, BA</a>
            <a href="/degrees/english-ba/">English, BA</a><a href="/degrees/english-bs/">English, BS</a>
            <a href="/degrees/physics/">Physics, BS</a><a href="/degrees/chem-minor/">Chemistry Minor</a>
            """, "html.parser")
        fields = [{"name": name, "cip_code": code} for name, code in [
            ("Anthropology.", "4502"), ("Chemistry.", "4005"), ("English.", "2301"), ("Physics.", "4008")
        ]]
        pages = {
            source["index_url"]: index,
            "https://example.edu/degrees/anth/": BeautifulSoup("<h1>Anthropology Major, B.A.</h1>", "html.parser"),
            "https://example.edu/degrees/physics/": BeautifulSoup("<h1>Department of Physics</h1>", "html.parser"),
        }
        with patch("scripts.collect_program_links.Reader") as reader:
            reader.return_value.page.side_effect = lambda url: (url, pages[url])
            self.assertEqual(collect(source, fields), [("42", "4502", "3", "https://example.edu/degrees/anth/")])


class SchoolDiscoveryTests(IsolatedAsyncioTestCase):
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
