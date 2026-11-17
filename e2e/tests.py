"""Browser tests (Playwright) and accessibility checks (axe-core).

They start a real Django server and drive Chromium, so they are slower than
the unit tests and are tagged "e2e". CI runs them in their own job:

    python manage.py test --tag e2e        # only these
    python manage.py test --exclude-tag e2e  # everything else

Locally, install the browser once with `playwright install chromium`.
"""

import os

from axe_playwright_python.sync_playwright import Axe
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import tag
from playwright.sync_api import sync_playwright

from abtest.models import Click, Impression

# Playwright's sync API runs an event loop; Django refuses ORM calls from a
# thread that has one unless this is set. Test-only.
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")

# Pages every visitor can reach without logging in.
PUBLIC_PAGES = ["/", "/login/", "/signup/", "/fd986fa"]

# axe impact levels that fail the build. "moderate" and "minor" are printed
# but do not fail, so the team can fix them over time.
BLOCKING_IMPACTS = {"critical", "serious"}

# Known problems that already exist on main, as (path, axe rule id). Each one
# has an issue; remove the entry when that issue is fixed. Anything new still
# fails the build, so the list can only shrink.
KNOWN_ISSUES = {
    ("/", "color-contrast"),  # landing page pastel tags and grey text: see KNOWN_ISSUES_ISSUE
}


@tag("e2e")
class BrowserTestCase(StaticLiveServerTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        super().tearDownClass()

    def setUp(self):
        # A new context is a new visitor: fresh cookies, fresh session.
        # Reduced motion: scroll-reveal animations finish instantly, so checks
        # see the final colours instead of a half-faded frame.
        self.context = self.browser.new_context(reduced_motion="reduce")
        self.page = self.context.new_page()

    def tearDown(self):
        self.context.close()

    def url(self, path):
        return f"{self.live_server_url}{path}"


class ABTestFlowTests(BrowserTestCase):
    """The flow the course's grading bot follows, in a real browser."""

    def test_variant_is_stable_and_click_counts_once(self):
        self.page.goto(self.url("/fd986fa"))
        button = self.page.locator("button#abtest")
        self.assertEqual(button.count(), 1)
        variant = button.inner_text().strip()
        self.assertIn(variant, {"kudos", "thanks"})

        self.page.reload()
        self.assertEqual(self.page.locator("button#abtest").inner_text().strip(), variant)

        self.page.locator("button#abtest").click()
        self.page.wait_for_load_state()
        if self.page.locator("button#abtest").count():
            self.page.locator("button#abtest").click()  # a second click must not count
            self.page.wait_for_load_state()

        self.assertEqual(Impression.objects.count(), 1)
        self.assertEqual(Click.objects.count(), 1)
        self.assertEqual(Click.objects.get().variant, variant)

        stats = self.page.request.get(self.url("/fd986fa/stats")).json()
        self.assertEqual(stats["preferred"], variant)

    def test_two_visitors_count_two_impressions(self):
        self.page.goto(self.url("/fd986fa"))
        other = self.browser.new_context()
        try:
            other.new_page().goto(self.url("/fd986fa"))
        finally:
            other.close()
        self.assertEqual(Impression.objects.count(), 2)

    def test_no_horizontal_scroll_on_a_phone(self):
        self.page.set_viewport_size({"width": 375, "height": 812})
        self.page.goto(self.url("/fd986fa"))
        overflow = self.page.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth")
        self.assertFalse(overflow)


class AccessibilityTests(BrowserTestCase):
    """axe-core checks on the public pages (WCAG 2 A/AA rules)."""

    axe = Axe()

    def test_public_pages_have_no_serious_violations(self):
        failures = []
        for path in PUBLIC_PAGES:
            with self.subTest(path=path):
                self.page.goto(self.url(path))
                results = self.axe.run(self.page)
                for violation in results.response["violations"]:
                    line = f"{path}: [{violation['impact']}] {violation['id']} - {violation['help']}"
                    print(line)
                    known = (path, violation["id"]) in KNOWN_ISSUES
                    if violation["impact"] in BLOCKING_IMPACTS and not known:
                        failures.append(line)
        self.assertEqual(failures, [], "\n".join(failures))
