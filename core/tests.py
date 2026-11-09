import os
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db.utils import IntegrityError
from django.test import TestCase
from django.urls import reverse

from core.management.commands.seed import GRADER_ACCOUNTS
from core.models import Institution, Shortlist, ShortlistItem

# Passwords the tests inject through the environment, the same way Render does.
SEED_ENV = {
    "SEED_ADMIN_PASSWORD": "test-only-admin-password",
    "SEED_STUDENT_PASSWORD": "test-only-student-password",
}


class SeedEnvMixin:
    """Supply grader passwords through the environment, as deployment does."""

    def setUp(self):
        super().setUp()
        patcher = patch.dict(os.environ, SEED_ENV)
        patcher.start()
        self.addCleanup(patcher.stop)


class SkeletonSmokeTests(TestCase):
    def test_healthz_reports_database_ok(self):
        response = self.client.get(reverse("healthz"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_home_page_loads_without_login(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Admit Compass")


class HomePageTests(TestCase):
    def test_uses_shared_layout(self):
        response = self.client.get(reverse("home"))
        self.assertTemplateUsed(response, "base.html")
        self.assertContains(response, "data-theme-switch")

    def test_visitor_sees_sign_up_and_log_in(self):
        response = self.client.get(reverse("home"))
        self.assertContains(response, "Get started, it's free")
        self.assertContains(response, f'href="{reverse("signup")}"')
        self.assertContains(response, f'href="{reverse("login")}"')

    def test_signed_in_user_is_welcomed_without_sign_up_button(self):
        user = get_user_model().objects.create_user("a@example.com", "a@example.com", "pw-not-used-elsewhere")
        self.client.force_login(user)

        response = self.client.get(reverse("home"))

        self.assertContains(response, "Welcome back")
        self.assertContains(response, "a@example.com")
        self.assertNotContains(response, "Get started, it's free")

    def test_lists_the_features_and_the_ai_section(self):
        response = self.client.get(reverse("home"))
        for name in ("Search", "Shortlist", "Compare"):
            self.assertContains(response, f'<h3 class="feature-title">{name}</h3>', html=True)
        self.assertContains(response, "An advisor that shows its work.")
        self.assertContains(response, '<h3 class="ai-point-title">Grounded in real data</h3>', html=True)

    def test_after_shortlist_features_are_marked_as_coming_next(self):
        response = self.client.get(reverse("home"))
        for name in ("Essay planner", "Schools like Yale", "Essays that worked"):
            self.assertContains(response, f'<h3 class="feature-title">{name}</h3>', html=True)
        self.assertContains(response, '<span class="soon">Coming next</span>', count=3, html=True)

    def test_animated_answers_are_in_the_html_without_javascript(self):
        # app.js only replays these; the full text must already be server-rendered.
        response = self.client.get(reverse("home"))
        self.assertContains(response, "It matches 3 of your 4 priorities")
        self.assertContains(response, "Yale admits fewer than 1 in 10 applicants")


class SeedCommandTests(SeedEnvMixin, TestCase):
    """The seed runs on every Render deploy, so idempotence is a hard requirement."""

    def test_seed_is_idempotent(self):
        call_command("seed", verbosity=0)
        counts = (
            get_user_model().objects.count(),
            Institution.objects.count(),
            Shortlist.objects.count(),
            ShortlistItem.objects.count(),
        )

        call_command("seed", verbosity=0)

        self.assertEqual(
            counts,
            (
                get_user_model().objects.count(),
                Institution.objects.count(),
                Shortlist.objects.count(),
                ShortlistItem.objects.count(),
            ),
            "Running seed twice changed the row counts; it must be safe on every deploy.",
        )

    def test_grader_accounts_can_log_in(self):
        call_command("seed", verbosity=0)
        for spec in GRADER_ACCOUNTS:
            with self.subTest(username=spec["username"]):
                self.assertTrue(
                    self.client.login(
                        username=spec["username"],
                        password=SEED_ENV[spec["password_env"]],
                    ),
                    f"Grader account {spec['username']} could not log in.",
                )
                self.client.logout()

    def test_admin_account_reaches_the_django_admin(self):
        call_command("seed", verbosity=0)
        self.client.login(
            username="admin", password=SEED_ENV["SEED_ADMIN_PASSWORD"]
        )
        self.assertEqual(self.client.get("/admin/").status_code, 200)

    def test_seeded_rows_are_labelled_as_sample_data(self):
        call_command("seed", verbosity=0)
        self.assertTrue(Institution.objects.exists())
        self.assertFalse(
            Institution.objects.exclude(data_release=Institution.SAMPLE).exists(),
            "Seeded rows must be labelled SAMPLE so demo data is never shown as federal data.",
        )
        self.assertEqual(Institution.objects.first().scorecard_url, "")


class SeedPasswordSourceTests(TestCase):
    """Grader passwords must never come from the repository."""

    def test_no_grader_password_is_committed(self):
        for spec in GRADER_ACCOUNTS:
            with self.subTest(username=spec["username"]):
                self.assertNotIn("password", spec, "Passwords must not be stored in code.")
                self.assertIn("password_env", spec)

    def test_seed_refuses_to_run_when_the_password_is_not_configured(self):
        """DEBUG is off under the test runner, as it is on staging and production."""
        with patch.dict(os.environ):
            for spec in GRADER_ACCOUNTS:
                os.environ.pop(spec["password_env"], None)
            with self.assertRaises(CommandError) as ctx:
                call_command("seed", verbosity=0)
        self.assertIn("SEED_ADMIN_PASSWORD", str(ctx.exception))
        self.assertEqual(
            get_user_model().objects.count(), 0, "A refused seed must not create accounts."
        )


class InstitutionModelTests(SeedEnvMixin, TestCase):
    def test_missing_metrics_stay_null_rather_than_zero(self):
        """Scorecard suppresses figures for small schools; 0 would become a real number."""
        call_command("seed", verbosity=0)
        suppressed = Institution.objects.get(unitid=900006)
        self.assertIsNone(suppressed.admission_rate)
        self.assertIsNone(suppressed.sat_average)

    def test_real_rows_expose_a_checkable_source_link(self):
        institution = Institution.objects.create(
            unitid=130794, name="Example Real University", data_release="2024-25"
        )
        self.assertFalse(institution.is_sample)
        self.assertEqual(
            institution.scorecard_url, "https://collegescorecard.ed.gov/school/?130794"
        )

    def test_a_school_cannot_appear_twice_on_one_shortlist(self):
        user = get_user_model().objects.create_user("dup", password="x-not-a-real-password")
        institution = Institution.objects.create(unitid=900099, name="Dup College")
        shortlist = Shortlist.objects.create(user=user, name="List")
        ShortlistItem.objects.create(shortlist=shortlist, institution=institution)
        with self.assertRaises(IntegrityError):
            ShortlistItem.objects.create(shortlist=shortlist, institution=institution)
