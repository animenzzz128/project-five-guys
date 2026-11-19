"""Per-user AI usage limits.  Owner: Package 2.

`ai.client.complete_json` calls `check_and_record` before every LLM request.
For now it allows everything; Package 2 replaces the body with a real daily
limit that raises `ai.client.AILimitReached` once a user has used it up.
"""


def check_and_record(user_obj, task):
    """Allow (and record) one `task` call for `user_obj`, or raise AILimitReached."""
    return None
