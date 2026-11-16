from unittest.mock import patch

from bs4 import BeautifulSoup
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase

from scripts.collect_program_links import collect

from .models import Institution, Program


class CollectorTests(SimpleTestCase):
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


class ApplyCatalogLinksTests(TestCase):
    def test_rerun_withdrawal_and_editor_override(self):
        school = Institution.objects.create(unitid=42, name="Example University")
        key = (42, "0101", 3)
        field = Program.objects.create(institution=school, name="Agriculture", degree="Bachelor's degree",
                                       credential_level=3, cip_code=key[1])
        official = "https://example.edu/degrees/agriculture/"
        with patch("core.management.commands.apply_catalog_links.read_links", return_value={key: official}):
            call_command("apply_catalog_links")
        field.refresh_from_db()
        self.assertEqual(field.catalog_url, official)
        with patch("core.management.commands.apply_catalog_links.read_links", return_value={}):
            call_command("apply_catalog_links")
        field.refresh_from_db()
        self.assertEqual(field.catalog_url, "")
        field.catalog_url = "https://example.edu/new-catalog/agriculture/"
        field.save()
        with patch("core.management.commands.apply_catalog_links.read_links", return_value={key: official}):
            call_command("apply_catalog_links")
        field.refresh_from_db()
        self.assertEqual(field.catalog_url, "https://example.edu/new-catalog/agriculture/")

    def test_invalid_snapshot_does_not_apply_partial_update(self):
        school = Institution.objects.create(unitid=42, name="Example University")
        field = Program.objects.create(institution=school, name="Agriculture", degree="Bachelor's degree",
                                       credential_level=3, cip_code="0101")
        links = {(42, "0101", 3): "https://example.edu/ag/", (42, "9999", 3): "https://example.edu/unknown/"}
        with patch("core.management.commands.apply_catalog_links.read_links", return_value=links):
            with self.assertRaises(CommandError):
                call_command("apply_catalog_links")
        field.refresh_from_db()
        self.assertEqual(field.catalog_url, "")
