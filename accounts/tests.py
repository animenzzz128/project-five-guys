from django.contrib.auth import SESSION_KEY, get_user_model
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages import get_messages
from django.contrib.staticfiles import finders
from django.template.loader import render_to_string
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse

from .models import ApplicantType, Profile

User = get_user_model()

GOOD_PASSWORD = "maple-orbit-lantern-42"


class SignupTests(TestCase):
    url = reverse("signup")

    def post(self, email="Student@Example.com", p1=GOOD_PASSWORD, p2=None, kind="high_school", **extra):
        data = {"applicant_type": kind, "email": email, "password1": p1, "password2": p2 if p2 is not None else p1}
        data.update(extra)
        return self.client.post(self.url, data)

    def test_page_renders_form(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "base.html")
        self.assertContains(response, 'name="email"')
        self.assertContains(response, "csrfmiddlewaretoken")

    def test_valid_signup_creates_user_logs_in_and_redirects_home(self):
        response = self.post()
        self.assertRedirects(response, "/", fetch_redirect_response=False)
        user = User.objects.get()
        self.assertEqual(user.email, "student@example.com")
        self.assertEqual(user.username, "student@example.com")
        self.assertTrue(user.check_password(GOOD_PASSWORD))
        self.assertEqual(int(self.client.session[SESSION_KEY]), user.pk)

    def test_duplicate_email_is_rejected_case_insensitively(self):
        User.objects.create_user("student@example.com", "student@example.com", GOOD_PASSWORD)
        response = self.post(email="STUDENT@example.com")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already exists")
        self.assertEqual(User.objects.count(), 1)

    def test_email_used_as_someone_elses_username_is_rejected(self):
        User.objects.create_user("student@example.com", "", GOOD_PASSWORD)
        response = self.post(email="student@example.com")
        self.assertContains(response, "already exists")

    def test_mismatched_passwords_are_rejected(self):
        response = self.post(p2="something-else-entirely-9")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.exists())
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_weak_password_is_rejected(self):
        response = self.post(p1="12345678")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.exists())

    def test_invalid_email_is_rejected(self):
        response = self.post(email="not-an-email")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.exists())

    def test_safe_next_is_followed(self):
        response = self.post(email="a@example.com", next="/fd986fa")
        self.assertRedirects(response, "/fd986fa", fetch_redirect_response=False)

    def test_offsite_next_is_ignored(self):
        response = self.post(next="https://evil.example.com/")
        self.assertRedirects(response, "/", fetch_redirect_response=False)

    def test_applicant_type_is_saved_on_a_profile(self):
        self.post(kind="professional")
        user = User.objects.get()
        self.assertEqual(user.profile.applicant_type, ApplicantType.PROFESSIONAL)
        self.assertEqual(Profile.for_user(user).get_applicant_type_display(), "Working professional")

    def test_applicant_type_is_required(self):
        response = self.post(kind="")
        self.assertContains(response, "Choose the option that describes you best.")
        self.assertFalse(User.objects.exists())

    def test_unknown_applicant_type_is_rejected(self):
        response = self.post(kind="astronaut")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.exists())
        self.assertFalse(Profile.objects.exists())

    def test_every_option_is_offered_and_accepted(self):
        page = self.client.get(self.url)
        for value, label in ApplicantType.choices:
            self.assertContains(page, f'value="{value}"')
            self.assertContains(page, label)
        for i, (value, _label) in enumerate(ApplicantType.choices):
            self.client.logout()
            self.post(email=f"user{i}@example.com", kind=value)
        self.assertEqual(Profile.objects.count(), len(ApplicantType.choices))

    def test_choice_is_kept_after_a_failed_attempt(self):
        response = self.post(kind="college", p2="does-not-match-9")
        self.assertContains(response, 'value="college" id="id_applicant_type_1" required checked')

    def test_no_user_is_left_behind_if_the_profile_fails(self):
        from unittest import mock

        with mock.patch.object(Profile.objects, "create", side_effect=RuntimeError("db down")):
            with self.assertRaises(RuntimeError):
                self.post()
        self.assertFalse(User.objects.exists())

    def test_logged_in_user_is_sent_home(self):
        user = User.objects.create_user("a@example.com", "a@example.com", GOOD_PASSWORD)
        self.client.force_login(user)
        response = self.client.get(self.url)
        self.assertRedirects(response, "/", fetch_redirect_response=False)

    def test_next_pointing_at_account_page_cannot_loop(self):
        user = User.objects.create_user("a@example.com", "a@example.com", GOOD_PASSWORD)
        self.client.force_login(user)
        for target in ("/signup/", "/login/", "/logout/"):
            response = self.client.get(f"{self.url}?next={target}")
            self.assertRedirects(response, "/", fetch_redirect_response=False)

    def test_next_survives_a_failed_attempt(self):
        response = self.client.post(self.url, {"email": "bad", "password1": "x", "password2": "y", "next": "/fd986fa"})
        self.assertContains(response, 'name="next" value="/fd986fa"')


class LoginTests(TestCase):
    url = reverse("login")

    @classmethod
    def setUpTestData(cls):
        cls.student = User.objects.create_user("student@example.com", "student@example.com", GOOD_PASSWORD)
        # Shape a seed command or createsuperuser might produce: username is not the email.
        cls.grader = User.objects.create_user("grader", "Grader@Example.com", GOOD_PASSWORD)

    def login(self, username, password=GOOD_PASSWORD, **extra):
        return self.client.post(self.url, {"username": username, "password": password, **extra})

    def assertLoggedInAs(self, user):
        self.assertEqual(int(self.client.session[SESSION_KEY]), user.pk)

    def test_page_renders_form(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Email")
        self.assertContains(response, "csrfmiddlewaretoken")

    def test_login_with_email(self):
        response = self.login("student@example.com")
        self.assertRedirects(response, "/", fetch_redirect_response=False)
        self.assertLoggedInAs(self.student)

    def test_login_email_is_case_and_space_insensitive(self):
        self.login("  Student@EXAMPLE.com ")
        self.assertLoggedInAs(self.student)

    def test_login_by_email_when_username_differs(self):
        self.login("grader@example.com")
        self.assertLoggedInAs(self.grader)

    def test_login_by_plain_username_still_works(self):
        self.login("grader")
        self.assertLoggedInAs(self.grader)

    def test_mixed_case_username_with_blank_email_can_log_in(self):
        user = User.objects.create_user("Coach@Example.com", "", GOOD_PASSWORD)
        self.login("Coach@Example.com")
        self.assertLoggedInAs(user)

    def test_exact_username_beats_someone_elses_email(self):
        # A's username is an address that B uses as their email: A must still get in as A.
        a = User.objects.create_user("bob@example.com", "", GOOD_PASSWORD)
        User.objects.create_user("bobby", "bob@example.com", GOOD_PASSWORD)
        self.login("bob@example.com")
        self.assertLoggedInAs(a)

    def test_shared_email_is_not_guessed(self):
        User.objects.create_user("twin1", "twin@example.com", GOOD_PASSWORD)
        User.objects.create_user("twin2", "twin@example.com", GOOD_PASSWORD)
        response = self.login("twin@example.com")
        self.assertContains(response, "don&#x27;t match")
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_inactive_user_cannot_log_in(self):
        User.objects.create_user("gone@example.com", "gone@example.com", GOOD_PASSWORD, is_active=False)
        self.login("gone@example.com")
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_blank_form_shows_errors_not_500(self):
        response = self.client.post(self.url, {"username": "", "password": ""})
        self.assertEqual(response.status_code, 200)

    def test_wrong_password_shows_error(self):
        response = self.login("student@example.com", "wrong-password")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "don&#x27;t match")
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_unknown_email_shows_same_error(self):
        response = self.login("nobody@example.com")
        self.assertContains(response, "don&#x27;t match")

    def test_next_is_followed(self):
        response = self.login("student@example.com", next="/fd986fa")
        self.assertRedirects(response, "/fd986fa", fetch_redirect_response=False)

    def test_offsite_or_script_next_is_ignored(self):
        for target in ("https://evil.example.com/", "//evil.example.com/", "javascript:alert(1)"):
            self.client.logout()
            response = self.login("student@example.com", next=target)
            self.assertRedirects(response, "/", fetch_redirect_response=False)

    def test_logged_in_visit_with_next_to_login_does_not_500(self):
        self.client.force_login(self.student)
        response = self.client.get(f"{self.url}?next=/login/")
        self.assertRedirects(response, "/", fetch_redirect_response=False)

    def test_next_survives_a_failed_attempt(self):
        response = self.login("student@example.com", "wrong", next="/fd986fa")
        self.assertContains(response, 'name="next" value="/fd986fa"')

    def test_success_message_is_queued(self):
        response = self.login("student@example.com")
        self.assertIn("You're logged in.", [str(m) for m in get_messages(response.wsgi_request)])

    def test_messages_render_in_layout(self):
        # Log in, log out, then open a base.html page: the queued message shows inline.
        self.login("student@example.com")
        self.client.post(reverse("logout"))
        response = self.client.get(reverse("login"))
        self.assertContains(response, "You&#x27;re logged out.")
        self.assertContains(response, '<div role="status">')

    def test_csrf_is_enforced(self):
        client = Client(enforce_csrf_checks=True)
        response = client.post(self.url, {"username": "student@example.com", "password": GOOD_PASSWORD})
        self.assertEqual(response.status_code, 403)

    def test_short_url_without_slash_redirects(self):
        response = self.client.get("/login")
        self.assertRedirects(response, "/login/", status_code=301, fetch_redirect_response=False)

    def test_settings_login_url_points_here(self):
        # settings.LOGIN_URL = "login"; @login_required pages must land on this view.
        from django.conf import settings
        from django.shortcuts import resolve_url

        self.assertEqual(resolve_url(settings.LOGIN_URL), "/login/")


class ProfileWithoutSignupTests(TestCase):
    def test_accounts_made_elsewhere_still_work(self):
        # createsuperuser / seed may create users without a Profile; nothing should break.
        user = User.objects.create_user("seeded@example.com", "seeded@example.com", GOOD_PASSWORD)
        self.assertIsNone(Profile.for_user(user))
        self.assertIsNone(Profile.for_user(AnonymousUser()))
        self.client.post(reverse("login"), {"username": "seeded@example.com", "password": GOOD_PASSWORD})
        self.assertEqual(int(self.client.session[SESSION_KEY]), user.pk)

    def test_profile_is_in_the_admin(self):
        from django.contrib import admin

        self.assertIn(Profile, admin.site._registry)


class LogoutTests(TestCase):
    url = reverse("logout")

    def setUp(self):
        self.user = User.objects.create_user("a@example.com", "a@example.com", GOOD_PASSWORD)
        self.client.force_login(self.user)

    def test_get_does_not_log_out(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 405)
        self.assertIn(SESSION_KEY, self.client.session)

    def test_post_logs_out_and_redirects_home(self):
        response = self.client.post(self.url)
        self.assertRedirects(response, "/", fetch_redirect_response=False)
        self.assertNotIn(SESSION_KEY, self.client.session)


class BaseLayoutTests(TestCase):
    """base.html is shared by every page, so check what other apps depend on."""

    def render(self, user=None):
        request = RequestFactory().get("/")
        request.user = user or AnonymousUser()
        return render_to_string("base.html", request=request)

    def test_anonymous_nav_offers_login_and_signup(self):
        html = self.render()
        self.assertIn('href="/login/"', html)
        self.assertIn('href="/signup/"', html)
        self.assertNotIn('action="/logout/"', html)

    def test_signed_in_nav_shows_email_and_post_logout(self):
        user = User.objects.create_user("a@example.com", "a@example.com", GOOD_PASSWORD)
        html = self.render(user)
        self.assertIn("a@example.com", html)
        self.assertIn('<form class="nav-logout" method="post" action="/logout/">', html)
        self.assertIn("csrfmiddlewaretoken", html)
        self.assertNotIn('href="/signup/"', html)

    def test_mobile_viewport_and_skip_link(self):
        html = self.render()
        self.assertIn('name="viewport"', html)
        self.assertIn('href="#main"', html)

    def test_no_popups_or_extra_buttons(self):
        # The A/B page extends this layout and must have no pop-up in the way and
        # exactly one <button id="abtest">, so the shell adds no dialogs and no ids.
        html = self.render()
        for marker in ("<dialog", 'role="dialog"', 'aria-modal', 'id="abtest"', "alert(", "confirm("):
            self.assertNotIn(marker, html)
        self.assertEqual(html.count("<button"), 1)  # only the theme switch (anonymous view)

    def test_field_errors_have_one_id_per_field(self):
        response = self.client.post(reverse("signup"), {"email": "", "password1": "1", "password2": "2"})
        html = response.content.decode()
        for name in ("email", "password2"):
            self.assertEqual(html.count(f'id="id_{name}_error"'), 1, name)

    def test_rotating_headline_is_readable_without_js(self):
        # The first word is in the HTML (no JS needed), and screen readers get one stable copy.
        response = self.client.get(reverse("login"))
        self.assertContains(response, '<span class="rotate-word spectrum" aria-hidden="true">who you are</span>')
        self.assertContains(response, '<span class="visually-hidden">who you are</span>')

    def test_no_third_party_font_or_script_requests(self):
        html = self.render()
        self.assertNotIn("fonts.googleapis.com", html)
        self.assertNotIn("<script src=\"http", html)

    def test_static_assets_exist(self):
        for path in ("css/app.css", "js/app.js", "img/compass.svg"):
            self.assertIsNotNone(finders.find(path), path)
