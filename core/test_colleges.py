from django.test import TestCase

from core.models import Institution


class CollegeSearchTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        rows = [
            (1, "University of Michigan-Ann Arbor", "MI", 1, 18000, 33000),
            (2, "Michigan Independent", "MI", 2, 40000, 2000),
            (3, "California Public", "CA", 1, None, None),
            (4, "Free College", "NY", 1, 0, 1100),
        ]
        for unit, name, state, owner, tuition, size in rows:
            Institution.objects.create(unitid=unit, name=name, state=state, ownership=owner,
                                       tuition_in_state=tuition, enrollment_undergrad=size, data_release="Federal")
        Institution.objects.create(unitid=10, name="Demo school", state="MI")

    def ids(self, **filters):
        response = self.client.get("/colleges/", filters)
        self.assertEqual(response.status_code, 200)
        return {s.unitid for s in response.context["page"]}

    def test_individual_and_combined_filters(self):
        self.assertEqual(self.ids(q="miCH"), {1, 2})
        self.assertEqual(self.ids(state=["CA", "MI"]), {1, 2, 3})
        self.assertEqual(self.ids(ownership="2"), {2})
        self.assertEqual(self.ids(tuition_max="18000"), {1, 4})
        self.assertEqual(self.ids(tuition_max="0"), {4})
        self.assertEqual(self.ids(size_min="2000", size_max="33000"), {1, 2})
        self.assertEqual(self.ids(state=["MI"], ownership="1", size_min="3000"), {1})

    def test_empty_invalid_and_missing_data(self):
        self.assertContains(self.client.get("/colleges/", {"q": "nonexistent"}), "Clear all filters")
        self.assertContains(self.client.get("/colleges/", {"size_min": 2, "size_max": 1}), "at least as large")
        self.assertContains(self.client.get("/colleges/3/"), "Not reported")
        self.assertEqual(self.client.get("/colleges/99999/").status_code, 404)

    def test_pagination_preserves_repeated_filters(self):
        Institution.objects.bulk_create([Institution(unitid=100+i, name=f"Michigan school {i}", state="MI",
                                                     data_release="Federal") for i in range(26)])
        response = self.client.get("/colleges/", {"q": "mich", "state": ["MI", "NY"]})
        self.assertEqual(len(response.context["page"]), 25)
        self.assertContains(response, 'q=mich&amp;state=MI&amp;state=NY&amp;page=2')
        self.assertEqual(len(self.ids(q="mich", state=["MI", "NY"], page=2)), 3)

    def test_removing_one_filter_keeps_others_and_resets_pagination(self):
        from urllib.parse import parse_qs

        response = self.client.get("/colleges/", {"q": "MICH", "state": ["MI", "CA"], "page": 2, "tuition_max": 0})
        chips = {chip["label"]: parse_qs(chip["query"]) for chip in response.context["form"].active_filters()}
        self.assertEqual(chips["MI"], {"q": ["MICH"], "state": ["CA"], "tuition_max": ["0"]})
        self.assertEqual(chips["Tuition ≤ $0"], {"q": ["MICH"], "state": ["MI", "CA"]})

    def test_demo_is_labeled_when_only_sample_rows_exist(self):
        Institution.objects.exclude(data_release=Institution.SAMPLE).delete()
        self.assertContains(self.client.get("/colleges/"), "Demo dataset")
