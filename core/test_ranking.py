"""Soft-preference ranking and major matching for the hybrid college search (#38)."""

from decimal import Decimal

from django.test import TestCase

from core.models import Institution, Program
from core.ranking import FACTORS, match_majors, parse_prefer, rank

# unitid, name, cost, earnings, admit, size
ROWS = [
    (1, "Alpha College", 20000, 50000, "0.9000", 2000),
    (2, "Beta University", 40000, 80000, "0.2000", 20000),
    (3, "Gamma College", 30000, None, "0.5000", 8000),  # no earnings reported
    (4, "Delta Institute", None, None, None, None),  # reports almost nothing
]


class RankTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        for unit, name, cost, earnings, admit, size in ROWS:
            Institution.objects.create(unitid=unit, name=name, cost_attendance=cost, median_earnings_10yr=earnings,
                                       admission_rate=admit and Decimal(admit), enrollment_undergrad=size,
                                       data_release="Federal")

    def order(self, prefer, **kwargs):
        return [Institution.objects.get(pk=r.pk).unitid for r in rank(Institution.objects.all(), prefer, **kwargs)]

    def test_parse_prefer_keeps_known_factors_and_clamps_weights(self):
        self.assertEqual(parse_prefer(["low_cost:2", "high_earnings:9", "vibes:1", "small", "low_cost:3", "large:x"]),
                         [("low_cost", 3), ("high_earnings", 3), ("small", 1), ("large", 1)])

    def test_single_factor_direction(self):
        self.assertEqual(self.order([("low_cost", 1)])[:3], [1, 3, 2])
        self.assertEqual(self.order([("high_earnings", 1)])[:2], [2, 1])
        self.assertEqual(self.order([("selective", 1)])[:3], [2, 3, 1])
        self.assertEqual(self.order([("accessible", 1)])[:3], [1, 3, 2])
        self.assertEqual(self.order([("large", 1)])[:3], [2, 3, 1])

    def test_missing_values_are_not_zero_and_sort_last(self):
        # Delta reports no cost: it must not win "low cost" as if its cost were $0.
        self.assertEqual(self.order([("low_cost", 1)])[-1], 4)
        scores = {Institution.objects.get(pk=r.pk).unitid: r.score for r in rank(Institution.objects.all(),
                                                                                 [("low_cost", 1)])}
        self.assertEqual(scores[4], 0)

    def test_weights_change_the_winner(self):
        self.assertEqual(self.order([("low_cost", 3), ("high_earnings", 1)])[0], 1)
        self.assertEqual(self.order([("low_cost", 1), ("high_earnings", 3)])[0], 2)

    def test_coverage_penalty_keeps_partial_data_from_winning(self):
        # Gamma is best-in-class on nothing it lacks, but it lacks earnings: with both weighted equally
        # a school reporting both figures should outrank one that only reports cost.
        ranked = rank(Institution.objects.all(), [("low_cost", 1), ("high_earnings", 1)])
        by_unit = {Institution.objects.get(pk=r.pk).unitid: r for r in ranked}
        self.assertLess(by_unit[3].score, by_unit[1].score)

    def test_ties_break_by_name(self):
        Institution.objects.create(unitid=5, name="Aardvark College", cost_attendance=20000, data_release="Federal")
        self.assertEqual(self.order([("low_cost", 1)])[:2], [5, 1])

    def test_reasons_use_database_figures(self):
        top = rank(Institution.objects.all(), [("low_cost", 1), ("high_earnings", 2)])[0]
        self.assertEqual(Institution.objects.get(pk=top.pk).unitid, 2)
        self.assertEqual(top.reasons[0], "Earnings $80,000 · higher than 100% of matches")
        self.assertEqual(len(top.reasons), 2)
        self.assertTrue(top.reasons[1].startswith("Cost $40,000"))

    def test_extra_scores_join_the_ranking(self):
        pk = {u: Institution.objects.get(unitid=u).pk for u in (1, 2, 3, 4)}
        extra = {pk[3]: (1.0, "Most similar to Yale"), pk[1]: (0.0, "")}
        ranked = rank(Institution.objects.all(), [("low_cost", 1)], extra=extra, extra_weight=3)
        self.assertEqual(ranked[0].pk, pk[3])
        self.assertIn("Most similar to Yale", ranked[0].reasons)

    def test_every_factor_reads_a_real_institution_field(self):
        fields = {f.name for f in Institution._meta.get_fields()}
        for factor in FACTORS.values():
            self.assertIn(factor.field, fields)


class MajorTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        a = Institution.objects.create(unitid=1, name="A", data_release="Federal")
        b = Institution.objects.create(unitid=2, name="B", data_release="Federal")
        for school in (a, b):
            Program.objects.create(institution=school, cip_code="1107", name="Computer Science.", credential_level=3,
                                   degree="Bachelor's degree")
        Program.objects.create(institution=a, cip_code="3008", name="Mathematics and Computer Science.",
                               credential_level=3, degree="Bachelor's degree")
        Program.objects.create(institution=b, cip_code="5138", name="Registered Nursing.", credential_level=2,
                               degree="Associate's degree")

    def test_keyword_finds_bachelor_fields_most_common_first(self):
        self.assertEqual(match_majors("computer science"),
                         [("1107", "Computer Science"), ("3008", "Mathematics and Computer Science")])

    def test_non_bachelor_records_do_not_count(self):
        self.assertEqual(match_majors("nursing"), [])

    def test_blank_or_unknown_keyword_matches_nothing(self):
        self.assertEqual(match_majors("  "), [])
        self.assertEqual(match_majors("underwater basket weaving"), [])
