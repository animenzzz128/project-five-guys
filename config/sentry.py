"""Privacy settings for Sentry error events.

`send_default_pii=False` alone is not enough: the SDK still attaches request
bodies (so a failed sign-up would carry the submitted email), query strings,
headers, and the local variables of every stack frame (whose `request` repr
includes the query string). These options keep the stack trace and the error
message, and drop all user input. config/tests.py proves it with a real event.
"""

# Keys of event["request"] that may carry user input or credentials.
_REQUEST_KEYS_TO_DROP = ("data", "query_string", "cookies", "headers", "env")


def scrub_event(event, hint):
    """before_send hook: strip anything a user typed or sent."""
    request = event.get("request")
    if isinstance(request, dict):
        for key in _REQUEST_KEYS_TO_DROP:
            request.pop(key, None)
    user = event.get("user")
    if isinstance(user, dict):
        event["user"] = {"id": user["id"]} if "id" in user else {}
    return event


SENTRY_PRIVACY_OPTIONS = {
    "send_default_pii": False,  # no IPs, cookies or logged-in user details
    "max_request_body_size": "never",  # never read form or JSON bodies
    "include_local_variables": False,  # frame locals can hold form data or the request
    "before_send": scrub_event,
}
