"""One-sentence college search (#38).  Owner: C.

Intent recognition, then hybrid retrieval. The LLM reads the student's
sentence once and returns structured intent (`schemas/search_parse.json`):
hard requirements (`must`), soft preferences (`prefer`), majors, a school to
compare with, and the wishes no field can express. Everything after that is
plain server code, so every result and every figure comes from our database:

- `normalize` checks and clamps the reply and maps it onto `/colleges/` query
  parameters: must -> filters, prefer -> `prefer=<factor>:<weight>`, majors ->
  `major=<keyword>` (only if our federal program data has such a field),
  "colleges like X" -> `similar_to=<unitid>` (only on exactly one name match;
  the LLM never supplies a UNITID). Regions become states through the fixed
  table in `regions.py`.
- `/colleges/` then filters on the hard requirements and ranks what is left by
  the preferences (`core/ranking.py`).
"""

import json
from pathlib import Path

from core.models import Institution
from core.ranking import FACTORS, MAX_WEIGHT, match_majors, prefer_param

from .client import complete_json
from .regions import REGIONS

SCHEMA = json.loads((Path(__file__).parent / "schemas" / "search_parse.json").read_text())
MAX_TEXT = 300
MAX_NAME = 255  # CollegeFilters.q max_length
MAX_TUITION = 100_000
MAX_COST = 150_000
MAX_EARNINGS = 500_000
MAX_SIZE = 500_000
MAX_MAJORS = 3

US_STATES = frozenset(
    "AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY "
    "NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split()
)
OWNERSHIP = {"public": Institution.Ownership.PUBLIC, "private": Institution.Ownership.PRIVATE_NONPROFIT}

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


def _shown_schools():
    """The rows `/colleges/` lists: real federal data once imported, else the demo seed."""
    schools = Institution.objects.exclude(data_release=Institution.SAMPLE)
    return schools if schools.exists() else Institution.objects.all()


def available_states():
    """States that actually have colleges in the list `/colleges/` shows."""
    return set(_shown_schools().exclude(state="").values_list("state", flat=True).distinct())


def find_school(name):
    """UNITIDs of the listed colleges whose name matches `name`, ignoring case (at most two)."""
    return list(_shown_schools().filter(name__iexact=name.strip()).values_list("unitid", flat=True)[:2])


def _whole(value, high):
    return None if value is None else str(min(max(int(value), 0), high))


def _fraction(value):
    return None if value is None else format(round(min(max(float(value), 0.0), 1.0), 4), "g")


def _range(params, notes, must, low_key, high_key, convert, label):
    """Copy a min/max pair; when min > max neither is applied and the student is told."""
    low, high = convert(must.get(low_key)), convert(must.get(high_key))
    if low is not None and high is not None and float(low) > float(high):
        notes.append({"phrase": f"{label} {low}–{high}", "reason": f"Minimum {label} is above the maximum"})
        return
    for value, key in ((low, low_key), (high, high_key)):
        if value is not None:
            params[key] = value


def normalize(raw, states_with_colleges, find_school=find_school, find_majors=match_majors):
    """Map a validated search_parse reply to `/colleges/` params plus notes for what was not applied.

    Returns (params, notes): params is {name: str | list[str]} in the list's own names; notes is
    [{"phrase", "reason"}] for the student to see. No value is guessed or defaulted here.
    """
    must = raw.get("must") or {}
    params, notes = {}, []

    name = (raw.get("name_query") or "").strip()[:MAX_NAME]
    if name:
        params["q"] = name

    states = []
    asked = [code.upper() for code in must.get("states") or []]
    for region in must.get("regions") or []:
        asked += [code for code in REGIONS[region] if code in states_with_colleges]
    for code in asked:
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

    for key, param, high in (("max_tuition", "tuition_max", MAX_TUITION), ("max_cost", "max_cost", MAX_COST),
                             ("min_earnings", "min_earnings", MAX_EARNINGS)):
        value = _whole(must.get(key), high)
        if value is not None:
            params[param] = value
    _range(params, notes, must, "size_min", "size_max", lambda v: _whole(v, MAX_SIZE), "size")
    _range(params, notes, must, "min_admit", "max_admit", _fraction, "admission rate")
    completion = _fraction(must.get("min_completion"))
    if completion is not None:
        params["min_completion"] = completion

    weights = {}
    for wish in raw.get("prefer") or []:
        if wish["factor"] in FACTORS:
            weight = min(max(int(wish.get("weight") or 1), 1), MAX_WEIGHT)
            weights[wish["factor"]] = max(weights.get(wish["factor"], 0), weight)
    if weights:
        params["prefer"] = [prefer_param(factor, weight) for factor, weight in weights.items()]

    majors = []
    for keyword in raw.get("majors") or []:
        keyword = " ".join(keyword.split()).lower()[:60]
        if not keyword or keyword in majors or len(majors) == MAX_MAJORS:
            continue
        if find_majors(keyword):
            majors.append(keyword)
        else:
            notes.append({"phrase": f"major: {keyword}", "reason": "No bachelor's program by that name in our data"})
    if majors:
        params["major"] = majors

    similar = (raw.get("similar_to_name") or "").strip()
    if similar:
        matches = find_school(similar)
        if len(matches) == 1:
            params["similar_to"] = str(matches[0])
        else:
            reason = "No college by that name in our data" if not matches else "Several colleges have that name"
            notes.append({"phrase": f"like {similar}", "reason": reason})

    for wish in raw.get("unsupported") or []:
        notes.append({"phrase": wish["phrase"], "reason": wish["reason"]})
    return params, notes
