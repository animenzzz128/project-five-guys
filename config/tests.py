"""Sentry must never send what a user typed (e.g. the email on a sign-up).

Requests go to a real live server (Django's WSGI handler, which is where the
SDK starts performance transactions; the test client skips that). Every test
captures EVERYTHING the SDK would send (errors, performance transactions and
any other envelope item) in memory, with tracing at 100%, and checks the fake
email, password and session cookie appear nowhere.
"""

import logging
import urllib.error
import urllib.parse
import urllib.request

import sentry_sdk
from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.test import LiveServerTestCase, override_settings
from django.urls import path
from django.views.decorators.csrf import csrf_exempt
from sentry_sdk.integrations.django import DjangoIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.transport import Transport

from config.sentry import SENTRY_PRIVACY_OPTIONS, scrub_event

# Built at runtime so the literals never appear in source lines Sentry attaches.
FAKE_EMAIL = "@".join(["pretend.student", "example.com"])
FAKE_PASSWORD = "-".join(["not", "a", "real", "password"])
# The same values as they appear inside a URL or form body (@ becomes %40).
SECRETS = {
    "email": FAKE_EMAIL,
    "url-encoded email": urllib.parse.quote(FAKE_EMAIL),
    "local part of the email": "pretend.student",
    "password": FAKE_PASSWORD,
    "session cookie": "sessionid",
}

logger = logging.getLogger("config.tests")


def broken_signup(request):
    raise RuntimeError("sign-up failed")


def lookup(request):
    # A DB query whose parameter is user input, plus a log line that (wrongly)
    # includes it: both must still be scrubbed.
    email = request.POST.get("email") or request.GET.get("email", "")
    get_user_model().objects.filter(email=email).exists()
    logger.info("looked up %s", email)
    return HttpResponse("ok")


def broken_with_input_in_message(request):
    raise ValueError(f"no account for {request.GET.get('email')}")


def logs_error_with_input(request):
    logger.error("sign-up failed for %s", request.POST.get("email"))
    return HttpResponse("ok")


# csrf_exempt: these test-only views take POSTs from urllib, which has no token.
urlpatterns = [
    path("broken-signup/", csrf_exempt(broken_signup)),
    path("lookup/", csrf_exempt(lookup)),
    path("broken-message/", csrf_exempt(broken_with_input_in_message)),
    path("log-error/", csrf_exempt(logs_error_with_input)),
]


class CapturingTransport(Transport):
    """Keeps every envelope item in memory instead of sending it anywhere."""

    def __init__(self, options=None):
        super().__init__(options)
        self.items = []

    def capture_envelope(self, envelope):
        for item in envelope.items:
            self.items.append((item.type, item.get_bytes().decode("utf-8", "replace")))

    def of_type(self, kind):
        return [body for item_type, body in self.items if item_type == kind]


@override_settings(ROOT_URLCONF=__name__, DEBUG_PROPAGATE_EXCEPTIONS=False)
class SentryPrivacyTests(LiveServerTestCase):
    def setUp(self):
        self.transport = CapturingTransport()
        sentry_sdk.init(
            dsn="https://public@sentry.example.invalid/1",
            transport=self.transport,
            integrations=[DjangoIntegration(), LoggingIntegration(event_level=logging.ERROR)],
            default_integrations=False,
            traces_sample_rate=1.0,  # worst case: every request is traced
            **SENTRY_PRIVACY_OPTIONS,
        )
        self.addCleanup(sentry_sdk.init)  # back to a no-op client

    def request(self, path, query=None, form=None):
        url = f"{self.live_server_url}{path}"
        if query:
            url += "?" + urllib.parse.urlencode(query)
        data = urllib.parse.urlencode(form).encode() if form else None
        req = urllib.request.Request(url, data=data, headers={"Cookie": "sessionid=abc"})
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                return response.status
        except urllib.error.HTTPError as error:
            return error.code

    def sent(self):
        sentry_sdk.flush()
        return self.transport.items

    def assert_nothing_leaked(self):
        items = self.sent()
        self.assertTrue(items, "expected Sentry to capture something")
        for item_type, body in items:
            for label, secret in SECRETS.items():
                self.assertNotIn(secret, body, f"{label} leaked in a {item_type}")

    def post(self, path):
        return self.request(path, query={"email": FAKE_EMAIL}, form={"email": FAKE_EMAIL, "password1": FAKE_PASSWORD})

    def test_error_event_from_failed_signup(self):
        self.post("/broken-signup/")
        self.assert_nothing_leaked()
        events = self.transport.of_type("event")
        self.assertEqual(len(events), 1)
        self.assertIn("sign-up failed", events[0])
        self.assertIn("/broken-signup/", events[0])  # still says where it broke

    def test_performance_transaction_of_successful_request(self):
        self.post("/lookup/")
        self.assert_nothing_leaked()
        transactions = self.transport.of_type("transaction")
        self.assertEqual(len(transactions), 1)
        self.assertIn("/lookup/", transactions[0])

    def test_get_request_with_email_in_url_is_traced_without_it(self):
        self.request("/lookup/", query={"email": FAKE_EMAIL})
        self.assert_nothing_leaked()
        self.assertEqual(len(self.transport.of_type("transaction")), 1)

    def test_exception_message_containing_input(self):
        self.request("/broken-message/", query={"email": FAKE_EMAIL})
        self.assert_nothing_leaked()
        self.assertIn("[email]", self.transport.of_type("event")[0])

    def test_error_log_containing_input(self):
        self.post("/log-error/")
        self.assert_nothing_leaked()
        self.assertTrue(self.transport.of_type("event"))

    def test_scrub_event_keeps_only_user_id(self):
        event = {"request": {"url": "/x", "data": {"email": FAKE_EMAIL}}, "user": {"id": 7, "email": FAKE_EMAIL}}
        scrubbed = scrub_event(event, None)
        self.assertEqual(scrubbed["request"], {"url": "/x"})
        self.assertEqual(scrubbed["user"], {"id": 7})
