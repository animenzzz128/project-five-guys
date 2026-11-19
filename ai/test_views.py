import os
from unittest import mock
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.test import TestCase

from ai.client import AILimitReached, AIUnavailable
from ai.models import SearchInterpretation
from ai.search import MAX_TEXT
from ai.testing import fake_ai
from core.models import Institution, Program

URL = "/colleges/ask/"


def query(response):
    parts = urlsplit(response["Location"])
    return parts.path, parse_qs(parts.query)


class AskViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="sam", email="sam@example.com", password="x")
        for unit, name, state, owner, tuition, size, cost, earnings in (
            (1, "Coastal Private College", "CT", 2, 58000, 9000, 59000, 82000),
            (2, "Big Public University", "MI", 1, 16000, 40000, 30000, 61000),
            (3, "Small Public College", "MA", 1, 14000, 3000, 26000, None),
            (4, "Pricey Private College", "NH", 2, 64000, 7000, 82000, 90000),
        ):
            Institution.objects.create(unitid=unit, name=name, state=state, ownership=owner, tuition_in_state=tuition,
                                       enrollment_undergrad=size, cost_attendance=cost, median_earnings_10yr=earnings,
                                       data_release="Federal")

    def setUp(self):
        self.client.force_login(self.user)

    def ask(self, text="a mid-sized private school in Connecticut", **extra):
        return self.client.post(URL, {"text": text, **extra})

    def messages(self, response):
        return [str(m) for m in response.wsgi_request._messages]

    def test_sentence_becomes_college_filters(self):
        reply = {"intent": "search", "must": {"states": ["CT", "ZZ"], "control": "private", "size_min": 5000,
                                              "size_max": 15000},
                 "unsupported": [{"phrase": "nice dorms", "reason": "No housing data"}]}
        with fake_ai([reply]) as calls:
            response = self.ask()
        path, params = query(response)
        interp = SearchInterpretation.objects.get()
        self.assertEqual(path, "/colleges/")
        self.assertEqual(params, {"state": ["CT"], "ownership": ["2"], "size_min": ["5000"],
                                  "size_max": ["15000"], "interp": [str(interp.pk)]})
        self.assertEqual(interp.user, self.user)
        self.assertEqual(interp.raw_json, reply)
        self.assertEqual(interp.notes, [{"phrase": "nice dorms", "reason": "No housing data"}])
        self.assertEqual(calls.call_args.args[0]["messages"][-1]["content"], "a mid-sized private school in Connecticut")
        page = self.client.get(response["Location"])
        self.assertContains(page, "Can't filter by:")
        self.assertContains(page, "nice dorms")
        self.assertContains(page, "AI understood:")

    def test_redirected_list_shows_the_matching_colleges(self):
        with fake_ai([{"must": {"control": "public", "size_max": 5000}}]):
            response = self.client.post(URL, {"text": "a small public college"}, follow=True)
        self.assertContains(response, "Small Public College")
        self.assertNotContains(response, "Big Public University")
        self.assertNotContains(response, "Coastal Private College")

    def test_acceptance_sentence_produces_matching_chips_and_list(self):
        reply = {"intent": "search",
                 "must": {"regions": ["northeast"], "control": "private", "size_min": 5000, "size_max": 15000,
                          "max_cost": 60000},
                 "prefer": [{"factor": "high_earnings", "weight": 2}]}
        sentence = "a mid-sized private school in the northeast under $60k a year where grads earn well"
        with fake_ai([reply]):
            response = self.client.post(URL, {"text": sentence}, follow=True)
        names = [school.name for school in response.context["page"]]
        self.assertEqual(names, ["Coastal Private College"])
        labels = {chip["label"] for chip in response.context["form"].active_filters()}
        self.assertEqual(labels, {"CT", "MA", "NH", "Private nonprofit", "Students ≥ 5,000", "Students ≤ 15,000",
                                  "Cost ≤ $60,000", "Prefers: higher earnings"})
        self.assertContains(response, "AI understood:")

    def test_similar_to_name_is_resolved_against_our_colleges(self):
        with fake_ai([{"intent": "similar", "similar_to_name": "coastal private college"},
                      {"intent": "similar", "similar_to_name": "Hogwarts"}]):
            found = self.ask(text="colleges like coastal private college")
            missing = self.ask(text="colleges like Hogwarts")
        self.assertEqual(query(found)[1]["similar_to"], ["1"])
        self.assertNotIn("similar_to", query(missing)[1])
        self.assertEqual(SearchInterpretation.objects.get(text="colleges like Hogwarts").notes[0]["phrase"],
                         "like Hogwarts")

    def test_another_users_interp_is_ignored(self):
        with fake_ai([{"unsupported": [{"phrase": "secret wish", "reason": "No data"}]}]):
            location = self.ask(text="my private sentence")["Location"]
        other = get_user_model().objects.create_user(username="eve", email="eve@example.com", password="x")
        self.client.force_login(other)
        page = self.client.get(location)
        self.assertEqual(page.status_code, 200)
        self.assertNotContains(page, "my private sentence")
        self.assertNotContains(page, "secret wish")
        self.assertNotContains(page, "AI understood:")
        self.client.logout()
        self.assertNotContains(self.client.get(location), "my private sentence")

    def test_bad_interp_values_are_ignored(self):
        for value in ("abc", "-1", "99999999999999999999999", "１"):
            self.assertEqual(self.client.get("/colleges/", {"interp": value}).status_code, 200)

    def test_removing_a_chip_keeps_the_interpretation(self):
        with fake_ai([{"must": {"control": "public", "size_max": 5000}}]):
            location = self.ask(text="a small public college")["Location"]
        page = self.client.get(location)
        chip = next(c for c in page.context["form"].active_filters() if c["label"] == "Students ≤ 5,000")
        after = self.client.get(f"/colleges/?{chip['query']}")
        self.assertContains(after, "a small public college")
        self.assertEqual({c["label"] for c in after.context["form"].active_filters()}, {"Public"})

    def test_out_of_scope_sentence_does_not_search(self):
        with fake_ai([{"intent": "out_of_scope"}]):
            response = self.ask(text="how do I write my Common App essay?")
        self.assertEqual(response["Location"], "/colleges/")
        self.assertIn("That doesn't look like a college search", self.messages(response)[0])
        self.assertEqual(self.client.session["ai_search_text"], "how do I write my Common App essay?")
        self.assertFalse(SearchInterpretation.objects.exists())

    def test_vague_wishes_rank_instead_of_excluding(self):
        reply = {"must": {"control": "public"}, "prefer": [{"factor": "low_cost", "weight": 2}]}
        with fake_ai([reply]):
            response = self.client.post(URL, {"text": "a cheap public college"}, follow=True)
        names = [school.name for school in response.context["page"]]
        self.assertEqual(names, ["Small Public College", "Big Public University"])  # cheapest first, none dropped
        self.assertContains(response, "Cost $26,000 · lower than 100% of matches")
        self.assertContains(response, "Prefers: lower cost")

    def test_majors_filter_by_bachelor_programs(self):
        for unit in (1, 3):
            Program.objects.create(institution=Institution.objects.get(unitid=unit), cip_code="5138",
                                   name="Registered Nursing.", credential_level=3, degree="Bachelor's degree")
        with fake_ai([{"majors": ["nursing", "wizardry"]}]):
            response = self.client.post(URL, {"text": "I want to study nursing or wizardry"}, follow=True)
        self.assertEqual({s.name for s in response.context["page"]}, {"Coastal Private College", "Small Public College"})
        self.assertContains(response, "Major: nursing")
        self.assertContains(response, "major: wizardry")  # listed under Can't filter by

    def test_example_button_is_used_as_the_sentence(self):
        with fake_ai([{"must": {"control": "public"}}]) as calls:
            self.ask(text="", example="A big public university")
        self.assertEqual(calls.call_args.args[0]["messages"][-1]["content"], "A big public university")

    def test_empty_text_makes_no_llm_call(self):
        with fake_ai([]) as calls:
            response = self.ask(text="   ")
        calls.assert_not_called()
        self.assertEqual(response["Location"], "/colleges/")
        self.assertIn("Describe your ideal college first.", self.messages(response))

    def test_too_long_text_makes_no_llm_call_and_is_kept(self):
        with fake_ai([]) as calls:
            response = self.ask(text="x" * (MAX_TEXT + 1))
        calls.assert_not_called()
        self.assertEqual(response["Location"], "/colleges/")
        self.assertEqual(len(self.client.session["ai_search_text"]), MAX_TEXT)
        self.assertFalse(SearchInterpretation.objects.exists())

    def test_ai_unavailable_falls_back_to_a_name_search(self):
        with fake_ai([AIUnavailable("down")]):
            response = self.ask(text="Michigan")
        self.assertEqual(query(response), ("/colleges/", {"q": ["Michigan"]}))
        self.assertIn("AI search is unavailable right now", self.messages(response)[0])
        self.assertFalse(SearchInterpretation.objects.exists())

    def test_bad_output_falls_back_to_a_name_search(self):
        with fake_ai(["not json", {"must": {"control": "maybe"}}]):
            response = self.ask(text="Michigan")
        self.assertEqual(query(response), ("/colleges/", {"q": ["Michigan"]}))

    def test_non_finite_numbers_fall_back_instead_of_500(self):
        with fake_ai(['{"must": {"min_admit": NaN}}', '{"must": {"min_admit": NaN}}']):
            response = self.client.post(URL, {"text": "Michigan"}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "AI search is unavailable right now")
        self.assertFalse(SearchInterpretation.objects.exists())

    def test_missing_key_falls_back_without_a_500(self):
        with mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": ""}), mock.patch("requests.post") as post:
            response = self.client.post(URL, {"text": "Michigan"}, follow=True)
        post.assert_not_called()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "AI search is unavailable right now")

    def test_daily_limit_keeps_the_text(self):
        with fake_ai([AILimitReached()]):
            response = self.ask(text="cheap schools")
        self.assertEqual(response["Location"], "/colleges/")
        self.assertIn("You've used today's AI searches.", self.messages(response))
        self.assertEqual(self.client.session["ai_search_text"], "cheap schools")

    def test_logged_out_users_are_sent_to_log_in(self):
        self.client.logout()
        with fake_ai([]) as calls:
            response = self.ask()
        calls.assert_not_called()
        self.assertTrue(response["Location"].startswith("/login/"))
        self.assertIn("next=/colleges/", response["Location"])

    def test_get_is_not_allowed(self):
        self.assertEqual(self.client.get(URL).status_code, 405)


class SearchBoxTests(TestCase):
    def test_logged_in_users_see_the_box_with_their_last_sentence(self):
        user = get_user_model().objects.create_user(username="kim", email="kim@example.com", password="x")
        self.client.force_login(user)
        session = self.client.session
        session["ai_search_text"] = "small schools <b>near</b> the coast"
        session.save()
        response = self.client.get("/colleges/")
        self.assertContains(response, 'action="/colleges/ask/"')
        self.assertContains(response, "small schools &lt;b&gt;near&lt;/b&gt; the coast")

    def test_logged_out_users_get_a_login_link(self):
        response = self.client.get("/colleges/")
        self.assertNotContains(response, 'action="/colleges/ask/"')
        self.assertContains(response, "/login/?next=/colleges/")
