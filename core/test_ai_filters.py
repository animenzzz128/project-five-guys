"""Filters, sort and "colleges like X" that the one-sentence AI search (#38) adds to /colleges/."""

from decimal import Decimal
from urllib.parse import parse_qs

from django.test import TestCase

from core.models import Institution, Program
from core.similarity import build_profiles

# unitid, name, state, owner, size, cost, admit, completion, earnings
ROWS = [
    (1, "Harbor College", "CT", 2, 5200, 61000, "0.1100", "0.8900", 79000),
    (2, "Ridge College", "MA", 2, 5000, 60000, "0.1000", "0.9000", 80000),
    (3, "Valley University", "MI", 1, 30000, 28000, "0.6000", "0.7000", 60000),
    (4, "Plains State", "KS", 1, 12000, 22000, "0.9000", "0.5000", 45000),
    (5, "Quiet College", "VT", 2, 1500, None, None, None, None),  # reports almost nothing
]


class AiFilterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        for unit, name, state, owner, size, cost, admit, completion, earnings in ROWS:
            Institution.objects.create(
                unitid=unit, name=name, state=state, ownership=owner, enrollment_undergrad=size,
                cost_attendance=cost, admission_rate=admit and Decimal(admit),
                completion_rate_150=completion and Decimal(completion), median_earnings_10yr=earnings,
                data_release="Federal",
            )
        build_profiles()

    def ids(self, **params):
        response = self.client.get("/colleges/", params)
        self.assertEqual(response.status_code, 200)
        return [school.unitid for school in response.context["page"]]

    def test_new_filters_skip_schools_that_do_not_report_the_figure(self):
        self.assertEqual(set(self.ids(max_cost="30000")), {3, 4})
        self.assertEqual(set(self.ids(min_earnings="70000")), {1, 2})
        self.assertEqual(set(self.ids(min_admit="0.5")), {3, 4})
        self.assertEqual(set(self.ids(max_admit="0.2")), {1, 2})
        self.assertEqual(set(self.ids(min_completion="0.85")), {1, 2})
        self.assertNotIn(5, self.ids(max_cost="1000000"))  # missing cost is never treated as 0

    def test_admit_min_above_max_is_an_error(self):
        response = self.client.get("/colleges/", {"min_admit": "0.6", "max_admit": "0.2"})
        self.assertEqual(list(response.context["page"]), [])
        self.assertContains(response, "at least as large")

    def test_sort_puts_missing_figures_last(self):
        self.assertEqual(self.ids(sort="cost"), [4, 3, 2, 1, 5])
        self.assertEqual(self.ids(sort="earnings"), [2, 1, 3, 4, 5])
        self.assertEqual(self.ids(sort="size"), [3, 4, 1, 2, 5])
        self.assertEqual(self.ids(sort="admit_rate"), [2, 1, 3, 4, 5])

    def test_similar_to_lists_closest_schools_first_without_the_school_itself(self):
        order = self.ids(similar_to="1")
        self.assertEqual(order[0], 2)
        self.assertNotIn(1, order)
        self.assertNotIn(5, order)  # too little data to compare

    def test_similar_to_combines_with_other_filters(self):
        public_in_similarity_order = [unitid for unitid in self.ids(similar_to="1") if unitid in (3, 4)]
        self.assertEqual(self.ids(similar_to="1", ownership="1"), public_in_similarity_order)
        self.assertEqual(self.ids(similar_to="1", state=["MA"]), [2])

    def test_similar_to_an_unknown_or_incomparable_school_lists_nothing(self):
        self.assertEqual(self.ids(similar_to="999"), [])
        self.assertEqual(self.ids(similar_to="5"), [])

    def test_sort_wins_over_similarity_order(self):
        self.assertEqual(self.ids(similar_to="1", sort="cost"), [4, 3, 2])

    def test_each_new_chip_removes_only_its_own_filter(self):
        response = self.client.get("/colleges/", {"max_cost": "70000", "min_admit": "0.05", "similar_to": "1",
                                                  "sort": "cost", "interp": "7"})
        chips = {chip["label"]: parse_qs(chip["query"]) for chip in response.context["form"].active_filters()}
        self.assertEqual(set(chips), {"Cost ≤ $70,000", "Admission ≥ 5%", "Like Harbor College", "Sorted by lowest cost"})
        self.assertEqual(chips["Like Harbor College"],
                         {"max_cost": ["70000"], "min_admit": ["0.05"], "sort": ["cost"], "interp": ["7"]})

    def test_hidden_filters_survive_apply_and_pagination(self):
        response = self.client.get("/colleges/", {"min_admit": "0.05", "similar_to": "1"})
        self.assertContains(response, 'type="hidden" name="min_admit" value="0.05"')
        self.assertContains(response, 'type="hidden" name="similar_to" value="1"')


class HybridRankingTests(TestCase):
    """prefer / major / sort=match / relax on /colleges/ (#38)."""

    @classmethod
    def setUpTestData(cls):
        AiFilterTests.setUpTestData.__func__(cls)
        for unit in (1, 3):
            Program.objects.create(institution=Institution.objects.get(unitid=unit), cip_code="1107",
                                   name="Computer Science.", credential_level=3, degree="Bachelor's degree")

    def page(self, **params):
        response = self.client.get("/colleges/", params)
        self.assertEqual(response.status_code, 200)
        return response

    def ids(self, **params):
        return [school.unitid for school in self.page(**params).context["page"]]

    def test_preferences_rank_by_default_and_keep_everyone(self):
        self.assertEqual(self.ids(prefer="low_cost:1"), [4, 3, 2, 1, 5])
        self.assertEqual(self.ids(prefer="high_earnings:1", ownership="2"), [2, 1, 5])

    def test_explicit_sort_overrides_match(self):
        self.assertEqual(self.ids(prefer="low_cost:1", sort="size"), [3, 4, 1, 2, 5])

    def test_match_order_survives_pagination(self):
        Institution.objects.bulk_create([Institution(unitid=100 + i, name=f"Filler {i:02}", cost_attendance=90000 + i,
                                                     data_release="Federal") for i in range(30)])
        first = self.ids(prefer="low_cost:1")
        second = self.ids(prefer="low_cost:1", page=2)
        self.assertEqual(first[:4], [4, 3, 2, 1])
        self.assertEqual(len(first), 25)
        self.assertEqual(second[-1], 5)  # no cost reported: last, after every school that reports one
        self.assertContains(self.page(prefer="low_cost:1"), "prefer=low_cost%3A1&amp;page=2")

    def test_reasons_show_database_figures(self):
        response = self.page(prefer="low_cost:1")
        self.assertEqual(response.context["page"][0].match_reasons, ["Cost $22,000 · lower than 100% of matches"])

    def test_major_filters_by_bachelor_programs(self):
        self.assertEqual(set(self.ids(major="computer science")), {1, 3})
        self.assertEqual(self.ids(major="underwater basket weaving"), [])

    def test_each_soft_and_major_chip_removes_only_itself(self):
        response = self.page(prefer=["low_cost:2", "high_earnings:1"], major=["computer science", "nursing"],
                             state=["CT", "MI"])
        chips = {chip["label"]: (chip["kind"], parse_qs(chip["query"])) for chip in
                 response.context["form"].active_filters()}
        self.assertEqual(chips["Prefers: lower cost"],
                         ("prefer", {"prefer": ["high_earnings:1"], "major": ["computer science", "nursing"],
                                     "state": ["CT", "MI"]}))
        self.assertEqual(chips["Major: nursing"][1]["major"], ["computer science"])
        self.assertContains(response, "chip-soft")

    def test_unknown_preference_values_are_ignored(self):
        self.assertEqual(self.ids(prefer=["vibes:3", "low_cost:x"]), [4, 3, 2, 1, 5])

    def test_similar_and_preferences_rank_together(self):
        ranked = self.page(similar_to="1", prefer="low_cost:1").context["page"]
        self.assertNotIn(1, [school.unitid for school in ranked])
        self.assertTrue(any("most similar to Harbor College" in reason for reason in ranked[0].match_reasons))

    def test_no_results_suggest_which_requirement_to_drop(self):
        response = self.page(state=["KS"], ownership="2", max_cost="30000")
        self.assertEqual(list(response.context["page"]), [])
        relax = response.context["relax"]
        # Only dropping "private" brings a school back (Plains State, public, $22,000);
        # dropping KS or the cost cap alone still leaves nothing, so they are not offered.
        self.assertEqual([option["label"] for option in relax], ["Private nonprofit"])
        self.assertEqual(relax[0]["count"], 1)
        self.assertContains(response, "Without “Private nonprofit”: 1 college")
