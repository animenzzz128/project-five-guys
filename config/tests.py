"""Sentry must never send what a user typed (e.g. the email on a failed sign-up)."""

import sentry_sdk
from django.http import HttpResponse
from django.test import SimpleTestCase, override_settings
from django.urls import path
from sentry_sdk.integrations.django import DjangoIntegration
from sentry_sdk.transport import Transport

from config.sentry import SENTRY_PRIVACY_OPTIONS, scrub_event

# Built at runtime so the literal never appears in source lines Sentry attaches.
FAKE_EMAIL = "@".join(["pretend.student", "example.com"])


def broken_signup(request):
    raise RuntimeError("sign-up failed")


def ok(request):
    return HttpResponse("ok")


urlpatterns = [path("broken-signup/", broken_signup), path("ok/", ok)]


class CapturingTransport(Transport):
    """Keeps events in memory instead of sending them anywhere."""

    def __init__(self, options=None):
        super().__init__(options)
        self.events = []

    def capture_envelope(self, envelope):
        for item in envelope.items:
            if item.type == "event":
                self.events.append(item.payload.json)


@override_settings(ROOT_URLCONF=__name__, DEBUG_PROPAGATE_EXCEPTIONS=False)
class SentryPrivacyTests(SimpleTestCase):
    def setUp(self):
        self.transport = CapturingTransport()
        sentry_sdk.init(
            dsn="https://public@sentry.example.invalid/1",
            transport=self.transport,
            integrations=[DjangoIntegration()],
            default_integrations=False,
            **SENTRY_PRIVACY_OPTIONS,
        )
        self.addCleanup(sentry_sdk.init)  # back to a no-op client

    def test_error_event_does_not_contain_submitted_email(self):
        self.client.raise_request_exception = False
        self.client.post(
            f"/broken-signup/?email={FAKE_EMAIL}",
            {"email": FAKE_EMAIL, "password1": "not-a-real-password"},
            HTTP_COOKIE="sessionid=abc",
        )
        sentry_sdk.flush()

        self.assertEqual(len(self.transport.events), 1)
        event = self.transport.events[0]
        self.assertIn("sign-up failed", str(event["exception"]))
        self.assertNotIn(FAKE_EMAIL, str(event))
        self.assertNotIn("not-a-real-password", str(event))
        self.assertNotIn("sessionid", str(event))
        self.assertEqual(event["transaction"], "/broken-signup/")  # still says where it broke

    def test_scrub_event_keeps_only_user_id(self):
        event = {"request": {"url": "/x", "data": {"email": FAKE_EMAIL}}, "user": {"id": 7, "email": FAKE_EMAIL}}
        scrubbed = scrub_event(event, None)
        self.assertEqual(scrubbed["request"], {"url": "/x"})
        self.assertEqual(scrubbed["user"], {"id": 7})
