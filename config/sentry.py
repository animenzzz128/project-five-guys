"""Privacy settings for everything the Sentry SDK sends.

`send_default_pii=False` alone is not enough. With Sentry on, user input can
leave the app through several channels, and each one is closed here:

- error events: request body, query string, headers, cookies, and the local
  variables of each stack frame (the `request` repr includes the query string)
- performance transactions (traces_sample_rate > 0): the request URL with its
  query string, and span data such as `http.query`
- breadcrumbs: log lines and SQL queries recorded before an error
- free text: an exception message or log line that includes an email

Every outgoing event, transaction and breadcrumb goes through `scrub_event` /
`scrub_breadcrumb`, which drop request input and replace anything that looks
like an email with "[email]". config/tests.py captures what the SDK would
really send, with tracing at 100%, and checks each channel.

Team rule that code cannot fully enforce: do not put user input other than
ids in exception messages or log lines. Email-shaped text is redacted, other
input (names, essay text) is not.
"""

import re

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
REDACTED_EMAIL = "[email]"

# Keys of a "request" block that may carry user input or credentials.
_REQUEST_KEYS_TO_DROP = ("data", "query_string", "cookies", "headers", "env")
# Span / breadcrumb data keys that hold a query string or full URL with it.
_DATA_KEYS_TO_DROP = ("http.query", "http.fragment")


def _redact(value):
    """Recursively replace email-shaped text in strings, lists and dicts."""
    if isinstance(value, str):
        return EMAIL_RE.sub(REDACTED_EMAIL, value)
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact(item) for item in value)
    if isinstance(value, dict):
        return {key: _redact(item) for key, item in value.items()}
    return value


def _strip_url_query(url):
    return url.split("?", 1)[0] if isinstance(url, str) else url


def _clean_request(request):
    if isinstance(request, dict):
        for key in _REQUEST_KEYS_TO_DROP:
            request.pop(key, None)
        if "url" in request:
            request["url"] = _strip_url_query(request["url"])


def _clean_data(data):
    if isinstance(data, dict):
        for key in _DATA_KEYS_TO_DROP:
            data.pop(key, None)
        for key in ("url", "http.url"):
            if key in data:
                data[key] = _strip_url_query(data[key])


def scrub_event(event, hint):
    """before_send and before_send_transaction hook."""
    _clean_request(event.get("request"))
    user = event.get("user")
    if isinstance(user, dict):
        event["user"] = {"id": user["id"]} if "id" in user else {}
    for span in event.get("spans") or []:
        _clean_data(span.get("data"))
        if isinstance(span.get("description"), str):
            span["description"] = _strip_url_query(span["description"])
    trace = (event.get("contexts") or {}).get("trace")
    if isinstance(trace, dict):
        _clean_data(trace.get("data"))
    return _redact(event)


def scrub_breadcrumb(crumb, hint):
    """before_breadcrumb hook: same rules for log lines, SQL and HTTP crumbs."""
    _clean_data(crumb.get("data"))
    return _redact(crumb)


SENTRY_PRIVACY_OPTIONS = {
    "send_default_pii": False,  # no IPs, cookies or logged-in user details
    "max_request_body_size": "never",  # never read form or JSON bodies
    "include_local_variables": False,  # frame locals can hold form data or the request
    "before_send": scrub_event,
    "before_send_transaction": scrub_event,
    "before_breadcrumb": scrub_breadcrumb,
}
