from django.test import SimpleTestCase

from ai.search import MAX_SIZE, MAX_TUITION, normalize

ALL = {"CT", "MA", "NY", "CA", "MI"}


def reasons(notes):
    return {note["phrase"]: note["reason"] for note in notes}


class NormalizeTests(SimpleTestCase):
    def test_maps_supported_fields_to_college_list_params(self):
        params, notes = normalize({
            "name_query": " Michigan ", "states": ["mi", "CT"], "control": "public",
            "max_tuition": 30000, "size_min": 2000, "size_max": 15000, "unsupported": [],
        }, ALL)
        self.assertEqual(params, {"q": "Michigan", "state": ["MI", "CT"], "ownership": "1",
                                  "tuition_max": "30000", "size_min": "2000", "size_max": "15000"})
        self.assertEqual(notes, [])

    def test_private_means_private_nonprofit(self):
        params, _ = normalize({"control": "private"}, ALL)
        self.assertEqual(params, {"ownership": "2"})

    def test_empty_and_null_values_are_dropped(self):
        params, notes = normalize({"name_query": "  ", "states": [], "control": None, "max_tuition": None}, ALL)
        self.assertEqual((params, notes), ({}, []))

    def test_invalid_state_codes_are_dropped(self):
        params, notes = normalize({"states": ["CT", "ZZ", "PR", "ct"]}, ALL)
        self.assertEqual(params, {"state": ["CT"]})
        self.assertEqual(notes, [])

    def test_valid_state_without_colleges_in_our_data_is_noted(self):
        params, notes = normalize({"states": ["CT", "TX"]}, ALL)
        self.assertEqual(params, {"state": ["CT"]})
        self.assertIn("TX", reasons(notes))

    def test_numbers_are_clamped(self):
        params, _ = normalize({"max_tuition": 900000, "size_min": -5, "size_max": 10 ** 9}, ALL)
        self.assertEqual(params, {"tuition_max": str(MAX_TUITION), "size_min": "0", "size_max": str(MAX_SIZE)})

    def test_float_numbers_become_whole_dollars(self):
        params, _ = normalize({"max_tuition": 45000.0}, ALL)
        self.assertEqual(params, {"tuition_max": "45000"})

    def test_min_above_max_drops_both_with_a_note(self):
        params, notes = normalize({"size_min": 20000, "size_max": 5000, "max_tuition": 10000}, ALL)
        self.assertEqual(params, {"tuition_max": "10000"})
        self.assertEqual(len(notes), 1)
        self.assertIn("size", notes[0]["reason"].lower())

    def test_llm_unsupported_wishes_are_kept(self):
        _, notes = normalize({"unsupported": [{"phrase": "great dorms", "reason": "No housing data"}]}, ALL)
        self.assertEqual(notes, [{"phrase": "great dorms", "reason": "No housing data"}])

    def test_fields_the_list_cannot_filter_yet_become_notes_not_filters(self):
        params, notes = normalize({"regions": ["northeast"], "max_cost": 40000, "min_admit": 0.3,
                                   "min_earnings": 70000, "similar_to_name": "Yale", "sort": "cost"}, ALL)
        self.assertEqual(params, {})
        self.assertEqual(len(notes), 6)

    def test_relevance_sort_is_not_a_note(self):
        self.assertEqual(normalize({"sort": "relevance"}, ALL), ({}, []))

    def test_name_query_is_truncated_to_the_form_limit(self):
        params, _ = normalize({"name_query": "x" * 400}, ALL)
        self.assertEqual(len(params["q"]), 255)


class SchemaTests(SimpleTestCase):
    def test_null_lists_are_valid(self):
        import jsonschema

        from ai.search import SCHEMA

        jsonschema.validate({"regions": None, "states": None, "unsupported": None, "control": None}, SCHEMA)
        self.assertEqual(normalize({"regions": None, "states": None, "unsupported": None}, ALL), ({}, []))
