import os
from unittest import mock

import requests
from django.test import SimpleTestCase

from ai import client
from ai.client import AIBadOutput, AILimitReached, AIUnavailable, complete_json
from ai.testing import fake_ai

SCHEMA = {
    "type": "object",
    "properties": {"city": {"type": "string"}, "size": {"type": ["integer", "null"]}},
    "required": ["city", "size"],
    "additionalProperties": False,
}
SECRET = "sk-or-v1-THIS-MUST-NEVER-BE-LOGGED"


def ask(**overrides):
    kwargs = {"task": "test_task", "system": "Extract the city.", "user": "Boston, please",
              "schema": SCHEMA, "user_obj": None}
    return complete_json(**{**kwargs, **overrides})


def http_reply(content, status=200):
    response = mock.Mock(status_code=status)
    response.json.return_value = {"choices": [{"message": {"content": content}}]}
    return response


class CompleteJsonTests(SimpleTestCase):
    def test_valid_reply_is_returned(self):
        with fake_ai([{"city": "Boston", "size": None}]) as calls:
            self.assertEqual(ask(), {"city": "Boston", "size": None})
        self.assertEqual(calls.call_count, 1)

    def test_request_asks_for_json_at_temperature_zero(self):
        with fake_ai([{"city": "Boston", "size": 1}]) as calls, \
                mock.patch.dict(os.environ, {"OPENROUTER_MODEL": "some/model"}):
            ask()
        payload = calls.call_args.args[0]
        self.assertEqual(payload["model"], "some/model")
        self.assertEqual(payload["temperature"], 0)
        self.assertEqual(payload["response_format"], {"type": "json_object"})
        self.assertIn('"required": ["city", "size"]', payload["messages"][0]["content"])
        self.assertEqual(payload["messages"][1], {"role": "user", "content": "Boston, please"})

    def test_model_defaults_when_unset(self):
        with fake_ai([{"city": "Boston", "size": 1}]) as calls, mock.patch.dict(os.environ, {"OPENROUTER_MODEL": ""}):
            ask()
        self.assertEqual(calls.call_args.args[0]["model"], client.DEFAULT_MODEL)

    def test_missing_key_is_unavailable_without_a_request(self):
        with mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": ""}), mock.patch("requests.post") as post:
            with self.assertRaises(AIUnavailable):
                ask()
        post.assert_not_called()

    def test_timeout_is_unavailable(self):
        with mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": SECRET}), \
                mock.patch("requests.post", side_effect=requests.Timeout("slow")):
            with self.assertRaises(AIUnavailable):
                ask()

    def test_network_error_is_unavailable(self):
        with mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": SECRET}), \
                mock.patch("requests.post", side_effect=requests.ConnectionError("dns")):
            with self.assertRaises(AIUnavailable):
                ask()

    def test_non_2xx_is_unavailable(self):
        with mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": SECRET}), \
                mock.patch("requests.post", return_value=http_reply("", status=502)):
            with self.assertRaises(AIUnavailable):
                ask()

    def test_unexpected_reply_shape_is_unavailable(self):
        response = mock.Mock(status_code=200)
        response.json.return_value = {"error": "nope"}
        with mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": SECRET}), \
                mock.patch("requests.post", return_value=response):
            with self.assertRaises(AIUnavailable):
                ask()

    def test_invalid_then_valid_returns_the_second_reply(self):
        with fake_ai([{"city": 42}, {"city": "Boston", "size": 3}]) as calls:
            self.assertEqual(ask(), {"city": "Boston", "size": 3})
        self.assertEqual(calls.call_count, 2)
        retry = calls.call_args_list[1].args[0]["messages"]
        self.assertEqual(retry[-2]["role"], "assistant")
        self.assertIn("invalid", retry[-1]["content"])

    def test_invalid_json_then_valid_returns_the_second_reply(self):
        with fake_ai(["not json at all", {"city": "Boston", "size": 3}]):
            self.assertEqual(ask(), {"city": "Boston", "size": 3})

    def test_fenced_json_is_accepted(self):
        with fake_ai(['```json\n{"city": "Boston", "size": 2}\n```']):
            self.assertEqual(ask(), {"city": "Boston", "size": 2})

    def test_invalid_twice_is_bad_output(self):
        with fake_ai([{"city": 1, "size": 1}, "still not json"]) as calls:
            with self.assertRaises(AIBadOutput):
                ask()
        self.assertEqual(calls.call_count, 2)

    def test_usage_is_checked_before_the_request(self):
        user = object()
        with fake_ai([]) as calls, mock.patch("ai.usage.check_and_record", side_effect=AILimitReached) as check:
            with self.assertRaises(AILimitReached):
                ask(user_obj=user, task="search_parse")
        check.assert_called_once_with(user, "search_parse")
        calls.assert_not_called()

    def test_key_is_never_logged(self):
        replies = [http_reply('{"city": "Boston", "size": 1}'), http_reply("", status=401)]
        with mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": SECRET}), \
                mock.patch("requests.post", side_effect=replies) as post, \
                self.assertLogs("ai.client", level="DEBUG") as logs:
            ask()
            with self.assertRaises(AIUnavailable) as raised:
                ask()
        self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], f"Bearer {SECRET}")
        self.assertNotIn(SECRET, "\n".join(logs.output))
        self.assertNotIn(SECRET, str(raised.exception))
        self.assertIn("outcome=ok", logs.output[0])
        self.assertIn("outcome=unavailable", logs.output[1])


VALID = '{"city": "Boston", "size": 1}'
HUGE_INT = '{"city": "Boston", "size": ' + "9" * 4400 + "}"
DEEP = "[" * 60000 + "]" * 60000  # json.loads raises RecursionError at this depth


def http_body(body, status=200):
    response = mock.Mock(status_code=status)
    response.json.return_value = body
    return response


class ProviderErrorTests(SimpleTestCase):
    """OpenRouter can report a failure inside an HTTP 200 reply (PR #39 review)."""

    def assert_unavailable(self, body):
        with mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": SECRET}), \
                mock.patch("requests.post", return_value=http_body(body)), \
                self.assertLogs("ai.client", level="INFO") as logs:
            with self.assertRaises(AIUnavailable):
                ask()
        self.assertIn("outcome=unavailable", logs.output[-1])

    def test_choice_error_with_valid_content_is_unavailable(self):
        self.assert_unavailable({"choices": [{"message": {"content": VALID}, "finish_reason": "stop",
                                              "error": {"code": 502, "message": "provider down"}}]})

    def test_finish_reason_error_with_valid_content_is_unavailable(self):
        self.assert_unavailable({"choices": [{"message": {"content": VALID}, "finish_reason": "error"}]})

    def test_top_level_error_in_a_200_is_unavailable(self):
        self.assert_unavailable({"error": {"code": 429, "message": "rate limited"},
                                 "choices": [{"message": {"content": VALID}}]})

    def test_normal_finish_reasons_still_succeed(self):
        for reason in ("stop", None):
            with mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": SECRET}), mock.patch(
                    "requests.post", return_value=http_body({"choices": [{"message": {"content": VALID},
                                                                          "finish_reason": reason}]})):
                self.assertEqual(ask(), {"city": "Boston", "size": 1})


class ParserLimitTests(SimpleTestCase):
    """Replies beyond the JSON parser's limits are bad output, never a stray exception (PR #39 review)."""

    def test_huge_integer_then_valid_retries_and_succeeds(self):
        with fake_ai([HUGE_INT, VALID]) as calls:
            self.assertEqual(ask(), {"city": "Boston", "size": 1})
        self.assertEqual(calls.call_count, 2)

    def test_huge_integer_twice_is_bad_output(self):
        with fake_ai([HUGE_INT, HUGE_INT]):
            with self.assertRaises(AIBadOutput):
                ask()

    def test_deep_nesting_then_valid_retries_and_succeeds(self):
        with fake_ai([DEEP, VALID]) as calls:
            self.assertEqual(ask(), {"city": "Boston", "size": 1})
        self.assertEqual(calls.call_count, 2)

    def test_deep_nesting_twice_is_bad_output(self):
        with fake_ai([DEEP, DEEP]):
            with self.assertRaises(AIBadOutput):
                ask()

    def test_recursion_error_maps_to_bad_output_even_without_the_length_cap(self):
        with mock.patch.object(client, "MAX_REPLY_CHARS", 10 ** 9), fake_ai([DEEP, VALID]) as calls:
            self.assertEqual(ask(), {"city": "Boston", "size": 1})
        self.assertEqual(calls.call_count, 2)
        with mock.patch.object(client, "MAX_REPLY_CHARS", 10 ** 9), fake_ai([DEEP, DEEP]):
            with self.assertRaises(AIBadOutput):
                ask()

    def test_overlong_reply_is_bad_output_without_parsing(self):
        with fake_ai(["x" * (client.MAX_REPLY_CHARS + 1), VALID]), mock.patch("json.loads",
                                                                              wraps=__import__("json").loads) as loads:
            self.assertEqual(ask(), {"city": "Boston", "size": 1})
        self.assertEqual(loads.call_count, 1)  # only the valid reply was parsed


class FakeAiTests(SimpleTestCase):
    def test_raises_exceptions_in_order(self):
        with fake_ai([AIUnavailable("down")]):
            with self.assertRaises(AIUnavailable):
                ask()

    def test_running_out_of_responses_fails_loudly(self):
        with fake_ai([]):
            with self.assertRaises(AssertionError):
                ask()

    def test_never_reaches_the_network(self):
        with fake_ai([{"city": "Boston", "size": 1}]), mock.patch("requests.post") as post:
            ask()
        post.assert_not_called()
