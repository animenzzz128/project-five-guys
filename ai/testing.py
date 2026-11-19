"""Test helper: run code that calls the LLM without touching the network.

    from ai.testing import fake_ai

    with fake_ai([{"name_query": "Yale"}, AIUnavailable("down")]) as calls:
        ...                       # 1st complete_json call returns the dict,
                                  # 2nd raises AIUnavailable
    calls.call_args_list          # the payloads that would have been sent

Each item is what the model "replies" for one request: a dict (sent back as
JSON, then validated against the caller's schema like a real reply), a str
(the raw reply text, e.g. to test invalid JSON), or an Exception to raise.
A retry inside complete_json consumes the next item. Using more items than
given fails the test.
"""

import json
import os
from contextlib import contextmanager
from unittest import mock

FAKE_KEY = "test-key-not-a-real-openrouter-key"


@contextmanager
def fake_ai(responses):
    queue = list(responses)

    def reply(payload, *, api_key, timeout):
        if not queue:
            raise AssertionError("fake_ai: the code made more LLM requests than responses were given")
        item = queue.pop(0)
        if isinstance(item, BaseException) or (isinstance(item, type) and issubclass(item, BaseException)):
            raise item
        return item if isinstance(item, str) else json.dumps(item)

    with mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": FAKE_KEY}), \
            mock.patch("ai.client._send", side_effect=reply) as calls:
        yield calls
