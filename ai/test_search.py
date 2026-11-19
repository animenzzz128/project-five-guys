import jsonschema
from django.test import SimpleTestCase

from ai.search import MAX_SIZE, MAX_TUITION, SCHEMA, normalize

ALL = {"CT", "MA", "NY", "CA", "MI"}
NO_SCHOOL = {"find_school": lambda name: [], "find_majors": lambda keyword: []}


def reasons(notes):
    return {note["phrase"]: note["reason"] for note in notes}


def must(**fields):
    return {"intent": "search", "must": fields}


def run(reply, **lookups):
    return normalize(reply, ALL, **{**NO_SCHOOL, **lookups})


class MustTests(SimpleTestCase):
    def test_maps_must_fields_to_college_list_params(self):
        params, notes = run({
            "intent": "search", "name_query": " Michigan ",
            "must": {"states": ["mi", "CT"], "control": "public", "max_tuition": 30000, "size_min": 2000,
                     "size_max": 15000, "max_cost": 40000, "min_earnings": 70000, "min_admit": 0.3,
                     "max_admit": 1.7, "min_completion": 0.65},
            "unsupported": [],
        })
        self.assertEqual(params, {"q": "Michigan", "state": ["MI", "CT"], "ownership": "1", "tuition_max": "30000",
                                  "max_cost": "40000", "min_earnings": "70000", "size_min": "2000",
                                  "size_max": "15000", "min_admit": "0.3", "max_admit": "1", "min_completion": "0.65"})
        self.assertEqual(notes, [])

    def test_private_means_private_nonprofit(self):
        self.assertEqual(run(must(control="private"))[0], {"ownership": "2"})

    def test_empty_and_null_values_are_dropped(self):
        empty = {"intent": "search", "name_query": "  ", "must": {"states": [], "control": None, "max_tuition": None},
                 "prefer": None, "majors": None}
        self.assertEqual(run(empty), ({}, []))
        self.assertEqual(run({"must": None}), ({}, []))

    def test_invalid_state_codes_are_dropped(self):
        self.assertEqual(run(must(states=["CT", "ZZ", "PR", "ct"])), ({"state": ["CT"]}, []))

    def test_valid_state_without_colleges_in_our_data_is_noted(self):
        params, notes = run(must(states=["CT", "TX"]))
        self.assertEqual(params, {"state": ["CT"]})
        self.assertIn("TX", reasons(notes))

    def test_regions_expand_to_states_with_colleges(self):
        params, notes = run(must(regions=["northeast", "pacific"], states=["NY"]))
        self.assertEqual((params, notes), ({"state": ["NY", "CT", "MA", "CA"]}, []))

    def test_numbers_are_clamped(self):
        params, _ = run(must(max_tuition=900000, size_min=-5, size_max=10 ** 9))
        self.assertEqual(params, {"tuition_max": str(MAX_TUITION), "size_min": "0", "size_max": str(MAX_SIZE)})

    def test_float_numbers_become_whole_dollars(self):
        self.assertEqual(run(must(max_tuition=45000.0))[0], {"tuition_max": "45000"})

    def test_min_above_max_drops_both_with_a_note(self):
        params, notes = run(must(size_min=20000, size_max=5000, max_tuition=10000))
        self.assertEqual(params, {"tuition_max": "10000"})
        self.assertIn("size", notes[0]["reason"])
        params, notes = run(must(min_admit=0.6, max_admit=0.2))
        self.assertEqual(params, {})
        self.assertIn("admission rate", notes[0]["reason"])

    def test_name_query_is_truncated_to_the_form_limit(self):
        self.assertEqual(len(run({"name_query": "x" * 400})[0]["q"]), 255)


class PreferTests(SimpleTestCase):
    def test_preferences_become_weighted_params_not_filters(self):
        params, notes = run({"prefer": [{"factor": "low_cost", "weight": 2}, {"factor": "high_earnings"},
                                        {"factor": "small", "weight": 7}, {"factor": "low_cost", "weight": 1}]})
        self.assertEqual(params, {"prefer": ["low_cost:2", "high_earnings:1", "small:3"]})
        self.assertEqual(notes, [])


class MajorTests(SimpleTestCase):
    def test_known_majors_become_params_and_unknown_become_notes(self):
        found = {"computer science": [("1107", "Computer Science")], "nursing": [("5138", "Registered Nursing")]}
        params, notes = run({"majors": ["Computer  Science", "nursing", "computer science", "dragon taming"]},
                            find_majors=lambda keyword: found.get(keyword, []))
        self.assertEqual(params, {"major": ["computer science", "nursing"]})
        self.assertEqual(notes, [{"phrase": "major: dragon taming",
                                  "reason": "No bachelor's program by that name in our data"}])

    def test_at_most_three_majors(self):
        params, _ = run({"majors": ["a", "b", "c", "d"]}, find_majors=lambda keyword: [("1", keyword)])
        self.assertEqual(params, {"major": ["a", "b", "c"]})


class SimilarTests(SimpleTestCase):
    def test_found_once_becomes_a_unitid(self):
        reply = {"intent": "similar", "similar_to_name": "Yale University"}
        self.assertEqual(run(reply, find_school=lambda name: [130794]), ({"similar_to": "130794"}, []))

    def test_not_found_is_a_note(self):
        params, notes = run({"similar_to_name": "Hogwarts"})
        self.assertEqual(params, {})
        self.assertEqual(notes, [{"phrase": "like Hogwarts", "reason": "No college by that name in our data"}])

    def test_ambiguous_is_a_note(self):
        params, notes = run({"similar_to_name": "Westminster College"}, find_school=lambda name: [1, 2])
        self.assertEqual(params, {})
        self.assertEqual(notes[0]["reason"], "Several colleges have that name")


class UnsupportedTests(SimpleTestCase):
    def test_llm_unsupported_wishes_are_kept(self):
        _, notes = run({"unsupported": [{"phrase": "great dorms", "reason": "No housing data"}]})
        self.assertEqual(notes, [{"phrase": "great dorms", "reason": "No housing data"}])


class SchemaTests(SimpleTestCase):
    def test_null_lists_and_objects_are_valid(self):
        reply = {"intent": None, "must": {"regions": None, "states": None, "control": None}, "prefer": None,
                 "majors": None, "unsupported": None}
        jsonschema.validate(reply, SCHEMA)
        self.assertEqual(run(reply), ({}, []))

    def test_unknown_preference_factor_is_rejected(self):
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate({"prefer": [{"factor": "good_vibes"}]}, SCHEMA)

    def test_flat_v1_fields_are_rejected(self):
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate({"states": ["CT"]}, SCHEMA)

    def test_schema_factors_match_the_ranking_factors(self):
        from core.ranking import FACTORS

        enum = SCHEMA["properties"]["prefer"]["items"]["properties"]["factor"]["enum"]
        self.assertEqual(set(enum), set(FACTORS))
