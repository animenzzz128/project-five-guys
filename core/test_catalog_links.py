from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from .models import Institution, Program


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
