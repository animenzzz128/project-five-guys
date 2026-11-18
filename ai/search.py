"""One-sentence college search (#38).  Owner: C.

The LLM only turns the student's sentence into structured filters
(`schemas/search_parse.json`). Everything after that is plain server code:
`normalize` checks and clamps those filters and maps them onto the
`/colleges/` query parameters (#7), so every result and every figure still
comes from our database.

Sprint 2 maps the filters the list already supports: name, state, school
type, in-state tuition and size. The other schema fields (regions, cost,
admission rate, earnings, completion, "similar to", sort) are kept as notes,
never guessed into a filter; Sprint 3 turns them into real filters.
"""

import json
from pathlib import Path

from core.models import Institution

from .client import complete_json

SCHEMA = json.loads((Path(__file__).parent / "schemas" / "search_parse.json").read_text())
MAX_TEXT = 300
MAX_NAME = 255  # CollegeFilters.q max_length
MAX_TUITION = 100_000
MAX_SIZE = 500_000

US_STATES = frozenset(
    "AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY "
    "NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split()
)
OWNERSHIP = {"public": Institution.Ownership.PUBLIC, "private": Institution.Ownership.PRIVATE_NONPROFIT}
NOT_YET = "Not available as a filter yet"
LATER_FIELDS = {
    "regions": "region", "max_cost": "total cost of attendance", "min_admit": "minimum admission rate",
    "max_admit": "maximum admission rate", "min_earnings": "graduate earnings",
    "min_completion": "graduation rate", "similar_to_name": "similar to a school", "sort": "sort order",
}

SYSTEM_PROMPT = """You turn one sentence from a prospective U.S. undergraduate student into search filters for a
college list. The sentence may be in English or Chinese. Only fill a field when the sentence asks for it; leave
every other field null (or an empty list). Never invent a school, a number the student did not imply, or a filter
for something the fields cannot express.

Fields:
- name_query: part of a college name the student typed, only if they named a school to search for.
- regions / states: where. Use states (two-letter codes) when the student names states; regions for broad areas.
- control: "public" or "private".
- max_tuition: in-state tuition ceiling in US dollars per year. max_cost: total cost of attendance ceiling.
- size_min / size_max: number of undergraduates.
- min_admit / max_admit: admission rate as a fraction 0-1. min_completion: graduation rate 0-1.
- min_earnings: median earnings ten years after entry, US dollars.
- similar_to_name: a school the student wants colleges "like"; copy the name exactly as written.
- sort: only if the student says how to order results.
- unsupported: every wish no field can express (majors, campus vibe, weather, sports, dorms, safety, ...),
  as {"phrase": the student's words, "reason": a short reason}. Never turn these into other filters.

Defaults for vague words (use exactly these numbers):
- "cheap", "affordable", "not too expensive" -> max_cost 40000
- "under $X a year" with no other context -> max_cost X
- "in-state tuition under $X" -> max_tuition X
- "small" -> size_max 5000; "mid-sized" -> size_min 5000 and size_max 15000; "big" or "large" -> size_min 15000
- "good salaries", "grads earn well" -> min_earnings 70000
- "not too hard to get into" -> min_admit 0.3; "selective" -> max_admit 0.3"""


def parse_sentence(text, user):
    """Ask the LLM for filters. Raises ai.client.AIUnavailable / AIBadOutput / AILimitReached."""
    return complete_json(task="search_parse", system=SYSTEM_PROMPT, user=text, schema=SCHEMA, user_obj=user)


def available_states():
    """States that actually have colleges in the list `/colleges/` shows (real data, else the demo seed)."""
    schools = Institution.objects.exclude(data_release=Institution.SAMPLE)
    if not schools.exists():
        schools = Institution.objects.all()
    return set(schools.exclude(state="").values_list("state", flat=True).distinct())


def _whole(value, high):
    return None if value is None else str(min(max(int(value), 0), high))


def normalize(raw, states_with_colleges):
    """Map a validated search_parse reply to `/colleges/` params plus notes for what was not applied.

    Returns (params, notes): params is {name: str | list[str]} in #7's names; notes is
    [{"phrase", "reason"}] for the student to see. No value is guessed or defaulted here.
    """
    params, notes = {}, []

    name = (raw.get("name_query") or "").strip()[:MAX_NAME]
    if name:
        params["q"] = name

    states = []
    for code in raw.get("states") or []:
        code = code.upper()
        if code not in US_STATES or code in states:
            continue
        if code in states_with_colleges:
            states.append(code)
        else:
            notes.append({"phrase": code, "reason": "No colleges from this state in our data"})
    if states:
        params["state"] = states

    if raw.get("control") in OWNERSHIP:
        params["ownership"] = str(OWNERSHIP[raw["control"]].value)

    tuition = _whole(raw.get("max_tuition"), MAX_TUITION)
    if tuition is not None:
        params["tuition_max"] = tuition

    low, high = _whole(raw.get("size_min"), MAX_SIZE), _whole(raw.get("size_max"), MAX_SIZE)
    if low is not None and high is not None and int(low) > int(high):
        notes.append({"phrase": f"{low}–{high} students", "reason": "Minimum size is above maximum size"})
    else:
        if low is not None:
            params["size_min"] = low
        if high is not None:
            params["size_max"] = high

    for field, label in LATER_FIELDS.items():
        value = raw.get(field)
        if value in (None, [], "", "relevance"):
            continue
        shown = ", ".join(value) if isinstance(value, list) else value
        notes.append({"phrase": f"{label}: {shown}", "reason": NOT_YET})

    for wish in raw.get("unsupported") or []:
        notes.append({"phrase": wish["phrase"], "reason": wish["reason"]})
    return params, notes
