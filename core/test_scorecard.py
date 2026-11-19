from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from .management.commands import import_scorecard
from .models import Institution, Program, Shortlist, ShortlistItem


class CatalogTests(TestCase):
    def setUp(self):
        self.school = Institution.objects.create(
            unitid=130794, name="Yale", data_release="previous", school_url="https://www.yale.edu/"
        )
        self.shortlist = Shortlist.objects.create(user=get_user_model().objects.create_user(username="student"))

    def test_federal_reimport_keeps_links_shortlists_and_specific_degrees(self):
        ShortlistItem.objects.create(shortlist=self.shortlist, institution=self.school)
        detail = Program.objects.create(institution=self.school, name="Computer Science", degree="BA")
        field = {"unitid": "130794", "cip_code": "0101", "name": "Agriculture", "credential_level": "3"}

        def records(filename):
            if filename == "institutions.csv.gz":
                return iter([{"unitid": "130794", "name": "Yale University", "region": "1"}])
            return iter([field.copy()])

        with patch.object(import_scorecard, "records", side_effect=records):
            import_scorecard.import_institutions()
            self.school.refresh_from_db()
            self.assertEqual(self.school.region, 1)
            ids = {self.school.unitid: self.school.pk}
            import_scorecard.import_fields(ids)
            federal = Program.objects.get(credential_level=3)
            federal.catalog_url = "https://example.edu/agriculture/"
            federal.save()
            field["name"] = "Updated field title"
            import_scorecard.import_fields(ids)

        federal.refresh_from_db()
        self.assertEqual(federal.name, "Updated field title")
        self.assertEqual(federal.cip_code, "0101")
        self.assertEqual(federal.catalog_url, "https://example.edu/agriculture/")
        self.assertEqual(self.shortlist.institutions.get(), self.school)
        self.assertTrue(Program.objects.filter(pk=detail.pk).exists())
        self.assertEqual(Program.objects.count(), 2)

    def test_unknown_school_rolls_back_specific_program_import(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "programs.csv"
            path.write_text(
                "unitid,name,degree,catalog_url\n130794,CS,BA,https://example.edu/cs/\n9999,CS,BA,https://example.edu/cs/\n"
            )
            with self.assertRaises(CommandError):
                call_command("import_programs", str(path))
        self.assertFalse(Program.objects.exists())

    def test_search_distinguishes_program_catalog_from_school_homepage(self):
        Program.objects.create(institution=self.school, name="Biology", degree="Bachelor's degree")
        Program.objects.create(
            institution=self.school, name="Computer Science", degree="BA", catalog_url="https://example.edu/cs/"
        )
        response = self.client.get("/programs/", {"q": "Yale"})
        self.assertContains(response, 'href="https://example.edu/cs/">Official program catalog')
        self.assertContains(response, 'href="https://www.yale.edu/">College website')
        self.assertNotContains(self.client.get("/programs/", {"q": "Physics"}), "Official program catalog")

    def test_program_search_ignores_null_characters(self):
        biology = Program.objects.create(institution=self.school, name="Biology", degree="BA")
        history = Program.objects.create(institution=self.school, name="History", degree="BA")
        for raw, cleaned, expected in (
            (" Bio\x00logy ", "Biology", [biology]),
            ("\x00", "", [biology, history]),
        ):
            with self.subTest(query=raw):
                response = self.client.get("/programs/", {"q": raw})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context["query"], cleaned)
                self.assertEqual(list(response.context["page"]), expected)
