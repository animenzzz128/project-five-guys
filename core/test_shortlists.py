from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from .management.commands.seed import Command, DEMO_SHORTLIST_NAME
from .models import Institution, Shortlist, ShortlistItem


class ShortlistFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.student = get_user_model().objects.create_user("student", password="sample-pass")
        cls.other = get_user_model().objects.create_user("other")
        Institution.objects.bulk_create([Institution(unitid=100+n, name=f"Campus {n}") for n in range(20)])

    def test_login_return_and_post_only(self):
        self.assertRedirects(self.client.get("/shortlist/"), "/login/?next=/shortlist/", fetch_redirect_response=False)
        res = self.client.post("/shortlist/add/100/", {"next": "/colleges/100/"})
        self.assertRedirects(res, "/login/?next=/colleges/100/", fetch_redirect_response=False)
        self.assertEqual(self.client.get("/shortlist/add/100/").status_code, 405)
        self.assertEqual(self.client.get("/shortlist/remove/1/").status_code, 405)

    def test_save_twenty_duplicate_and_confirmed_removal(self):
        self.client.force_login(self.student)
        for n in range(20):
            self.client.post(f"/shortlist/add/{100+n}/")
        self.client.post("/shortlist/add/100/")
        self.assertContains(self.client.get("/shortlist/"), "20 saved")
        school = Institution.objects.get(unitid=100)
        item = ShortlistItem.objects.get(institution=school)
        other_list = Shortlist.objects.create(user=self.other)
        other_item = ShortlistItem.objects.create(institution=school, shortlist=other_list)
        url = reverse("shortlist_remove", args=[item.pk])
        self.assertContains(self.client.get("/colleges/100/"), url)
        self.assertContains(self.client.get("/colleges/"), url)
        self.assertContains(self.client.post(url), "Confirm removal")
        self.assertTrue(ShortlistItem.objects.filter(pk=item.pk).exists())
        self.assertRedirects(self.client.post(url, {"confirm": "yes"}), "/shortlist/")
        self.assertContains(self.client.get("/shortlist/"), "19 saved")
        self.assertContains(self.client.get("/colleges/100/"), "Add to shortlist")
        self.assertTrue(ShortlistItem.objects.filter(pk=other_item.pk).exists())

    def test_private_named_lists_and_csrf(self):
        private = Shortlist.objects.create(user=self.other, name="Private research")
        item = ShortlistItem.objects.create(shortlist=private, institution=Institution.objects.get(unitid=100))
        self.client.force_login(self.student)
        self.assertNotContains(self.client.get("/shortlist/"), "Private research")
        self.assertEqual(self.client.post(reverse("shortlist_remove", args=[item.pk]),
                                          {"confirm": "yes"}).status_code, 404)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.student)
        self.assertEqual(csrf_client.post("/shortlist/add/100/").status_code, 403)
        self.assertEqual(csrf_client.post(reverse("shortlist_remove", args=[item.pk])).status_code, 403)

    def test_reseeding_respects_existing_lists_and_removed_items(self):
        command = Command()
        command._seed_institutions()
        command._seed_demo_shortlist(self.student)
        initial = Shortlist.objects.get(user=self.student, name=DEMO_SHORTLIST_NAME)
        item = initial.items.first()
        unit = item.institution.unitid
        self.client.force_login(self.student)
        self.client.post(f"/shortlist/add/{unit}/")
        self.assertEqual(self.student.shortlists.count(), 1)
        self.client.post(reverse("shortlist_remove", args=[item.pk]), {"confirm": "yes"})
        command._seed_demo_shortlist(self.student)
        self.assertFalse(initial.items.filter(institution__unitid=unit).exists())
