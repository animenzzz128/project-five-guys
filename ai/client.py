"""The one place this app talks to an LLM.  Owner: C.

Every AI feature calls `complete_json`. It sends a chat request to OpenRouter
from the server (never from browser JavaScript), asks for a JSON object, and
returns it only after it validates against the caller's JSON Schema.

Configuration comes from the environment, never from git:

    OPENROUTER_API_KEY   required; without it every call raises AIUnavailable
    OPENROUTER_MODEL     optional; defaults to DEFAULT_MODEL

Tests never reach the network: wrap them in `ai.testing.fake_ai`.
"""

import json
import logging
import os
import time

import jsonschema
import requests

from . import usage

logger = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-4o-mini"
MAX_REPLY_CHARS = 20_000  # far above any real reply; bounds parsing work and memory


class AIUnavailable(Exception):
    """No key, network error, timeout, or a non-2xx / unreadable reply."""


class AIBadOutput(Exception):
    """The model's reply was not valid JSON for the schema, even after one retry."""


class AILimitReached(Exception):
    """The user has used up their AI allowance (raised by ai.usage.check_and_record)."""


def complete_json(*, task: str, system: str, user: str, schema: dict, user_obj, timeout: float = 15) -> dict:
    """Ask the model for a JSON object matching `schema` and return it.

    Raises AIUnavailable, AIBadOutput or AILimitReached; never returns invalid data.
    """
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    model = os.environ.get("OPENROUTER_MODEL", "").strip() or DEFAULT_MODEL
    started = time.monotonic()
    outcome = "error"
    try:
        if not api_key:
            outcome = "unavailable"
            raise AIUnavailable("OPENROUTER_API_KEY is not set")
        try:
            usage.check_and_record(user_obj, task)
        except AILimitReached:
            outcome = "limit"
            raise

        messages = [
            {"role": "system", "content": _with_schema(system, schema)},
            {"role": "user", "content": user},
        ]
        for attempt in (1, 2):
            payload = {
                "model": model,
                "messages": messages,
                "temperature": 0,
                "response_format": {"type": "json_object"},
            }
            try:
                content = _send(payload, api_key=api_key, timeout=timeout)
            except AIUnavailable:
                outcome = "unavailable"
                raise
            try:
                result = _parse(content, schema)
            except AIBadOutput as error:
                if attempt == 2:
                    outcome = "bad_output"
                    raise
                messages = [
                    *messages,
                    {"role": "assistant", "content": content},
                    {"role": "user", "content": f"That reply was invalid: {error}. "
                                                "Reply again with only a JSON object that matches the schema."},
                ]
                continue
            outcome = "ok" if attempt == 1 else "ok_after_retry"
            return result
    finally:
        latency_ms = round((time.monotonic() - started) * 1000)
        logger.info("ai task=%s model=%s latency_ms=%d outcome=%s", task, model, latency_ms, outcome)


def _with_schema(system, schema):
    return (f"{system}\n\nReply with one JSON object holding your answer, and nothing else. "
            f"Do not repeat the schema itself. The object must be valid against this JSON Schema:\n"
            f"{json.dumps(schema)}")


def _send(payload, *, api_key, timeout):
    """POST one chat request and return the reply text.  The only network call."""
    headers = {"Authorization": f"Bearer {api_key}", "X-Title": "Admit Compass"}
    try:
        response = requests.post(OPENROUTER_URL, json=payload, headers=headers, timeout=timeout)
    except requests.Timeout as error:
        raise AIUnavailable("OpenRouter timed out") from error
    except requests.RequestException as error:
        raise AIUnavailable(f"OpenRouter request failed: {type(error).__name__}") from error
    if not 200 <= response.status_code < 300:
        raise AIUnavailable(f"OpenRouter returned HTTP {response.status_code}")
    try:
        body = response.json()
        choice = body["choices"][0] if isinstance(body, dict) and "error" not in body else None
    except (ValueError, KeyError, IndexError, TypeError) as error:
        raise AIUnavailable("OpenRouter reply had an unexpected shape") from error
    # OpenRouter can report a failure inside an HTTP 200: a top-level or choice-level
    # "error", or finish_reason "error". Never treat such a reply as an answer.
    if choice is None or not isinstance(choice, dict) or choice.get("error") or choice.get("finish_reason") == "error":
        raise AIUnavailable("OpenRouter reported an error in its reply")
    try:
        content = choice["message"]["content"]
    except (KeyError, TypeError) as error:
        raise AIUnavailable("OpenRouter reply had an unexpected shape") from error
    if not isinstance(content, str):
        raise AIUnavailable("OpenRouter reply had no text content")
    return content


def _parse(content, schema):
    """Reply text -> validated dict, or AIBadOutput. Every parser failure maps to AIBadOutput."""
    if len(content) > MAX_REPLY_CHARS:
        raise AIBadOutput(f"reply too long ({len(content)} characters)")
    text = content.strip()
    if text.startswith("```"):  # some models wrap JSON in a Markdown fence
        text = text.strip("`").removeprefix("json").strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise AIBadOutput(f"not valid JSON ({error.msg})") from error
    except (ValueError, RecursionError) as error:  # e.g. a 4,400-digit integer, or nesting too deep
        raise AIBadOutput(f"JSON beyond parser limits ({type(error).__name__})") from error
    try:
        jsonschema.validate(data, schema)
    except jsonschema.ValidationError as error:
        where = "/".join(str(part) for part in error.absolute_path) or "(root)"
        raise AIBadOutput(f"schema mismatch at {where}: {error.message}") from error
    except RecursionError as error:
        raise AIBadOutput("JSON nested too deeply to validate") from error
    return data
