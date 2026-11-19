"""Tests for "Find similar" (#16).  Owner: B."""

import os
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db.models import Q
from django.test import TestCase
from django.urls import reverse

from core.models import Institution, SimilarityProfile
from core.similarity import NotComparable, build_profiles, similar_institutions

REAL = "Scorecard test"


def school(unitid, name, size, cost, admit, completion, earnings, *, ownership=2, region=1, release=REAL):
    return Institution.objects.create(
        unitid=unitid, name=name, state="CT", ownership=ownership, region=region, data_release=release,
        enrollment_undergrad=size, cost_attendance=cost, admission_rate=admit,
        completion_rate_150=completion, median_earnings_10yr=earnings,
    )


class SimilarityFixture(TestCase):
    """A source school, three neighbours at known distances, a twin with a gap, and a thin row."""

    def setUp(self):
        self.source = school(1, "Source College", 5000, 60000, "0.1000", "0.9000", 80000)
        self.near = school(2, "Near College", 5200, 61000, "0.1100", "0.8900", 79000)
        self.middle = school(3, "Middle College", 8000, 50000, "0.3000", "0.8000", 70000)
        self.far = school(4, "Far University", 30000, 25000, "0.8000", "0.5000", 40000, ownership=1, region=5)
        # Same as the source except it does not report an admission rate.
        self.twin = school(5, "Twin College", 5000, 60000, None, "0.9000", 80000)
        # Only two figures reported: too little to compare.
        self.thin = Institution.objects.create(unitid=6, name="Thin Institute", data_release=REAL,
                                               enrollment_undergrad=900, cost_attendance=20000)
        build_profiles()


class RankingTests(SimilarityFixture):
    def ids(self, results):
        return [result.institution.unitid for result in results]

    def test_known_neighbour_order(self):
        self.assertEqual(self.ids(similar_institutions(1)), [5, 2, 3, 4])

    def test_never_includes_the_source_school(self):
        for unitid in (1, 2, 3, 4, 5):
            self.assertNotIn(unitid, self.ids(similar_institutions(unitid)))

    def test_missing_value_is_left_out_not_treated_as_zero(self):
        twin = similar_institutions(1)[0]
        # Identical on every figure both report; a 0 admission rate would have pushed it away.
        self.assertEqual(twin.institution, self.twin)
        self.assertAlmostEqual(twin.distance, 0.0)
        self.assertNotIn("Similar admission rate", [reason["label"] for reason in twin.reasons])
        profile = SimilarityProfile.objects.get(institution=self.twin)
        self.assertFalse(profile.present & (1 << 2))

    def test_each_result_has_two_or_three_reasons_with_real_figures(self):
        for result in similar_institutions(1):
            self.assertGreaterEqual(len(result.reasons), 2)
            self.assertLessEqual(len(result.reasons), 3)
        near = next(r for r in similar_institutions(1) if r.institution == self.near)
        self.assertIn({"label": "Similar size", "detail": "5,200 undergraduates (Source College: 5,000)"},
                      near.reasons)

    def test_too_little_data_is_not_comparable(self):
        self.assertFalse(SimilarityProfile.objects.filter(institution=self.thin).exists())
        with self.assertRaises(NotComparable):
            similar_institutions(6)

    def test_limit_exclude_and_filters(self):
        self.assertEqual(self.ids(similar_institutions(1, k=2)), [5, 2])
        self.assertEqual(self.ids(similar_institutions(1, exclude_ids={5, 2})), [3, 4])
        self.assertEqual(self.ids(similar_institutions(1, filters=Q(ownership=1))), [4])

    def test_demo_rows_are_never_mixed_with_federal_rows(self):
        school(900, "Demo Twin", 5000, 60000, "0.1000", "0.9000", 80000, release=Institution.SAMPLE)
        build_profiles()
        self.assertNotIn(900, self.ids(similar_institutions(1)))

    def test_rebuilding_is_idempotent(self):
        before = list(SimilarityProfile.objects.order_by("pk").values_list("pk", "present"))
        self.assertEqual(build_profiles(), 5)
        self.assertEqual(list(SimilarityProfile.objects.order_by("pk").values_list("pk", "present")), before)


class PageTests(SimilarityFixture):
    def test_similar_page_lists_matches_with_reasons(self):
        response = self.client.get(reverse("similar_colleges", args=[1]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Colleges like")
        self.assertContains(response, "Near College")
        self.assertContains(response, "Similar size")
        self.assertNotContains(response, 'href="/colleges/1/similar/"')  # no link to itself as a result
        self.assertLess(response.content.decode().index("Twin College"), response.content.decode().index("Far University"))

    def test_insufficient_data_shows_a_message_not_an_error(self):
        response = self.client.get(reverse("similar_colleges", args=[6]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Not enough data to compare")

    def test_unknown_school_is_404(self):
        self.assertEqual(self.client.get(reverse("similar_colleges", args=[999999])).status_code, 404)

    def test_rows_and_detail_pages_link_to_find_similar(self):
        link = reverse("similar_colleges", args=[2])
        self.assertContains(self.client.get(reverse("colleges")), link)
        self.assertContains(self.client.get(reverse("college_detail", args=[2])), link)

    def test_saved_state_shows_for_signed_in_user(self):
        user = get_user_model().objects.create_user("s@example.com", "s@example.com", "pw-for-tests-only")
        self.client.force_login(user)
        self.client.post(reverse("shortlist_add", args=[2]))
        response = self.client.get(reverse("similar_colleges", args=[1]))
        self.assertContains(response, "Remove from shortlist · Near College")
        self.assertContains(response, "Add to shortlist · Middle College")


class SeedTests(TestCase):
    def test_seed_builds_profiles_for_the_demo_data(self):
        env = {"SEED_ADMIN_PASSWORD": "test-only-admin", "SEED_STUDENT_PASSWORD": "test-only-student"}
        with patch.dict(os.environ, env):
            call_command("seed", stdout=open(os.devnull, "w"))
        self.assertTrue(SimilarityProfile.objects.exists())
        demo = Institution.objects.filter(data_release=Institution.SAMPLE).first()
        self.assertTrue(similar_institutions(demo.unitid))
