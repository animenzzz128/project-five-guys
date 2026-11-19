"""One-sentence college search (#38).  Owner: C.

Intent recognition, then retrieval. The LLM reads the student's sentence once
and returns structured intent (`schemas/search_parse.json`): hard requirements
(`must`), soft preferences (`prefer`), majors, a school to compare with, and
the wishes no field can express. Everything after that is plain server code:
`normalize` checks and clamps the reply and maps it onto the `/colleges/`
query parameters, so every result and every figure comes from our database.

This first version maps the hard requirements the list already filters by:
name, state, school type, in-state tuition and size. Everything else the
model understood is shown to the student as a note, never guessed into a
filter.
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
LATER_MUST = {
    "regions": "region", "max_cost": "total cost of attendance", "min_admit": "minimum admission rate",
    "max_admit": "maximum admission rate", "min_earnings": "graduate earnings", "min_completion": "graduation rate",
}

SYSTEM_PROMPT = """You read one sentence from a prospective U.S. undergraduate student describing the college they
want, and return their intent as structured search parameters. The sentence may be in English or Chinese. You never
answer the question yourself, never name or recommend schools, and never invent numbers.

intent:
- "search": they describe the kind of college they want (the usual case).
- "similar": they want colleges like a named school; put that name in similar_to_name exactly as written.
- "name_lookup": they only typed (part of) a college name; put it in name_query.
- "out_of_scope": not a request to find colleges (essays, visas, chit-chat). Leave everything else empty.

must = hard requirements, things a college has to satisfy:
- places the student names: states (two-letter codes) or regions (northeast = New England, mid_atlantic, south,
  midwest, southwest, west = Mountain West, pacific). "The Northeast" / "the East Coast" in everyday speech means
  both northeast and mid_atlantic.
- control: "public" or "private", only when stated.
- explicit numbers or limits: "under $40k a year" -> max_cost 40000; "in-state tuition under $15k" -> max_tuition
  15000; "fewer than 5,000 students" -> size_max 5000; "at least 20,000 students" -> size_min 20000;
  admission and graduation rates as fractions 0-1; min_earnings in US dollars.
- "mid-sized" is a range the student means literally: size_min 5000 and size_max 15000.

prefer = soft preferences: vague or comparative wishes that should rank colleges, not exclude them. Use only these
factors, weight 1 (nice to have), 2 (important) or 3 (the student stresses it, e.g. "most of all"):
  low_cost ("cheap", "affordable", "not too expensive"), low_tuition, high_earnings ("grads earn well",
  "good salaries"), high_completion ("people actually graduate"), high_retention, low_debt ("graduate without much
  debt"), selective ("prestigious", "hard to get into"), accessible ("not too hard to get into", "easy to get
  in"), small ("small", "close-knit"), large ("big school", "lots of students").
Do not also turn a preference into a must number.

majors: fields of study the student wants, in plain English as they would appear in a U.S. catalog
("computer science", "nursing", "mechanical engineering"); translate Chinese ("计算机" -> "computer science").

unsupported: every wish none of the above can express (campus vibe, weather, sports, dorms, safety, religion,
specific clubs, ...), as {"phrase": the student's own words, "reason": a short reason}. Never squeeze these into
other fields. Leave any field the sentence does not mention null or empty."""


def parse_sentence(text, user):
    """Ask the LLM for the sentence's intent. Raises ai.client.AIUnavailable / AIBadOutput / AILimitReached."""
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

    Returns (params, notes): params is {name: str | list[str]} in the list's names (#7); notes is
    [{"phrase", "reason"}] for the student to see. No value is guessed or defaulted here.
    """
    must = raw.get("must") or {}
    params, notes = {}, []

    name = (raw.get("name_query") or "").strip()[:MAX_NAME]
    if name:
        params["q"] = name

    states = []
    for code in must.get("states") or []:
        code = code.upper()
        if code not in US_STATES or code in states:
            continue
        if code in states_with_colleges:
            states.append(code)
        else:
            notes.append({"phrase": code, "reason": "No colleges from this state in our data"})
    if states:
        params["state"] = states

    if must.get("control") in OWNERSHIP:
        params["ownership"] = str(OWNERSHIP[must["control"]].value)

    tuition = _whole(must.get("max_tuition"), MAX_TUITION)
    if tuition is not None:
        params["tuition_max"] = tuition

    low, high = _whole(must.get("size_min"), MAX_SIZE), _whole(must.get("size_max"), MAX_SIZE)
    if low is not None and high is not None and int(low) > int(high):
        notes.append({"phrase": f"{low}–{high} students", "reason": "Minimum size is above maximum size"})
    else:
        if low is not None:
            params["size_min"] = low
        if high is not None:
            params["size_max"] = high

    for field, label in LATER_MUST.items():
        value = must.get(field)
        if value not in (None, [], ""):
            shown = ", ".join(value) if isinstance(value, list) else value
            notes.append({"phrase": f"{label}: {shown}", "reason": NOT_YET})
    for wish in raw.get("prefer") or []:
        notes.append({"phrase": f"preference: {wish['factor'].replace('_', ' ')}", "reason": NOT_YET})
    for major in raw.get("majors") or []:
        notes.append({"phrase": f"major: {major}", "reason": NOT_YET})
    if (raw.get("similar_to_name") or "").strip():
        notes.append({"phrase": f"like {raw['similar_to_name'].strip()}", "reason": NOT_YET})

    for wish in raw.get("unsupported") or []:
        notes.append({"phrase": wish["phrase"], "reason": wish["reason"]})
    return params, notes
