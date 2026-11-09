"""Tests for the A/B page. Each django.test.Client is one visitor (its own session)."""

import re
from unittest import mock

from django.test import Client, TestCase
from django.urls import reverse

from .models import Click, Impression
from .views import TEAM_NICKNAMES

PAGE = "/fd986fa"
STATS = "/fd986fa/stats"
BUTTON_RE = re.compile(r'<button\b[^>]*\bid="abtest"[^>]*>(.*?)</button>', re.S)


def button_texts(response):
    return [text.strip() for text in BUTTON_RE.findall(response.content.decode())]


class PageTests(TestCase):
    def test_urls_match_team_hash(self):
        self.assertEqual(reverse("abtest"), PAGE)
        self.assertEqual(reverse("abtest_stats"), STATS)

    def test_public_page_lists_team_and_has_one_server_rendered_button(self):
        response = self.client.get(PAGE)

        self.assertEqual(response.status_code, 200)
        for nickname in TEAM_NICKNAMES:
            self.assertContains(response, nickname)
        texts = button_texts(response)
        self.assertEqual(len(texts), 1)
        self.assertIn(texts[0], ("kudos", "thanks"))
        self.assertEqual(texts[0], self.client.session["abtest_variant"])
        self.assertNotContains(response, "<script")

    def test_reloading_keeps_variant_and_counts_one_impression(self):
        first = button_texts(self.client.get(PAGE))[0]
        for _ in range(9):
            self.assertEqual(button_texts(self.client.get(PAGE)), [first])

        self.assertEqual(Impression.objects.count(), 1)
        self.assertEqual(Impression.objects.get().variant, first)

    def test_new_visitors_get_both_variants(self):
        seen = set()
        for _ in range(60):  # chance of one variant missing: 2 * 0.5**60
            seen.update(button_texts(Client().get(PAGE)))
        self.assertEqual(seen, {"kudos", "thanks"})
        self.assertEqual(Impression.objects.count(), 60)

    def test_assignment_is_a_fair_coin_over_both_variants(self):
        real_choice = __import__("secrets").choice

        def fake_choice(options):
            # Django's session-key generator also uses secrets.choice; leave it alone.
            return "thanks" if options == ["kudos", "thanks"] else real_choice(options)

        with mock.patch("abtest.views.secrets.choice", side_effect=fake_choice) as choice:
            self.assertEqual(button_texts(self.client.get(PAGE)), ["thanks"])
        choice.assert_any_call(["kudos", "thanks"])

    def test_head_request_does_not_count_an_impression(self):
        self.assertEqual(self.client.head(PAGE).status_code, 200)
        self.assertEqual(Impression.objects.count(), 0)

    def test_impressions_and_clicks_have_timestamps(self):
        self.client.get(PAGE)
        self.client.post(PAGE)
        self.assertIsNotNone(Impression.objects.get().created_at)
        self.assertIsNotNone(Click.objects.get().created_at)


class ClickTests(TestCase):
    def test_clicking_twice_counts_one_click_and_keeps_one_impression(self):
        variant = button_texts(self.client.get(PAGE))[0]

        for _ in range(2):
            response = self.client.post(PAGE, follow=True)
            self.assertRedirects(response, PAGE)
            self.assertEqual(button_texts(response), [variant])

        self.assertEqual(Click.objects.count(), 1)
        self.assertEqual(Click.objects.get().variant, variant)
        self.assertEqual(Impression.objects.count(), 1)

    def test_click_without_seeing_the_page_is_ignored(self):
        response = self.client.post(PAGE)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Click.objects.count(), 0)
        self.assertEqual(Impression.objects.count(), 0)

    def test_real_form_post_passes_csrf(self):
        browser = Client(enforce_csrf_checks=True)
        page = browser.get(PAGE).content.decode()
        token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', page).group(1)

        response = browser.post(PAGE, {"csrfmiddlewaretoken": token})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Click.objects.count(), 1)

    def test_other_methods_are_rejected(self):
        self.assertEqual(self.client.put(PAGE).status_code, 405)


class StatsTests(TestCase):
    def add(self, variant, impressions, clicks):
        prefix = f"{variant}-{Impression.objects.count()}-"
        Impression.objects.bulk_create(
            Impression(visitor=f"{prefix}{i}", variant=variant) for i in range(impressions)
        )
        Click.objects.bulk_create(
            Click(visitor=f"{prefix}{i}", variant=variant) for i in range(clicks)
        )

    def test_works_with_no_data(self):
        response = self.client.get(STATS)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn(body["preferred"], ("kudos", "thanks"))
        self.assertEqual(body["kudos"], {"impressions": 0, "clicks": 0, "click_rate": 0.0})
        self.assertEqual(body["thanks"], {"impressions": 0, "clicks": 0, "click_rate": 0.0})

    def test_prefers_higher_click_rate_not_more_clicks(self):
        self.add("kudos", impressions=100, clicks=30)  # 30 clicks, 30%
        self.add("thanks", impressions=10, clicks=5)  # 5 clicks, 50%

        body = self.client.get(STATS).json()

        self.assertEqual(body["preferred"], "thanks")
        self.assertEqual(body["kudos"]["clicks"], 30)
        self.assertEqual(body["thanks"]["click_rate"], 0.5)

    def test_prefers_kudos_when_its_rate_is_higher(self):
        self.add("kudos", impressions=10, clicks=6)  # 60%
        self.add("thanks", impressions=50, clicks=20)  # 40%

        self.assertEqual(self.client.get(STATS).json()["preferred"], "kudos")

    def test_one_variant_without_impressions(self):
        self.add("thanks", impressions=4, clicks=1)

        self.assertEqual(self.client.get(STATS).json()["preferred"], "thanks")

    def test_counts_live_page_visits(self):
        visitor = Client()
        visitor.get(PAGE)
        visitor.post(PAGE)
        variant = visitor.session["abtest_variant"]

        body = self.client.get(STATS).json()

        self.assertEqual(body[variant], {"impressions": 1, "clicks": 1, "click_rate": 1.0})
        self.assertEqual(body["preferred"], variant)

    def test_stats_is_public_json_and_does_not_count_an_impression(self):
        response = self.client.get(STATS)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertEqual(Impression.objects.count(), 0)
