from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


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
