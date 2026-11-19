"""Hybrid college search, retrieval side (#38).  Owner: C.

The one-sentence search recognizes intent with an LLM (`ai/search.py`); this
module does the rest with our own data only:

- `match_majors(keyword)` finds the federal bachelor's fields of study whose
  name contains a keyword, for the `major` filter (recall).
- `rank(schools, prefer)` orders the candidates that passed the hard filters
  by the student's soft preferences (ranking). For each preference factor a
  school scores its percentile among the candidates that report that figure;
  its match is the weighted mean over the factors it reports, scaled by how
  much of the requested weight it could be judged on:

      match = sum(w * p) / sum(w over reported)      p = percentile in [0, 1]
      score = match * (0.5 + 0.5 * coverage)          coverage = reported w / all w

  A missing figure is never treated as 0 or as average: it is left out, and
  the coverage term keeps a school with little data from beating one that
  reports everything. Ties break by name. `extra` lets a caller add one more
  pre-scored signal (the "colleges like X" similarity); a later re-ranking
  step can take `rank()`'s output as its input.
"""

from bisect import bisect_left, bisect_right
from dataclasses import dataclass, field

from django.db.models import Count

from .models import Program


@dataclass(frozen=True)
class Factor:
    field: str
    higher_is_better: bool
    label: str  # chip text: "Prefers: lower cost"
    detail: str  # format for the school's own figure
    word: str  # "cheaper than 82% of matches"

    def show(self, value):
        return self.detail.format(float(value))


FACTORS = {
    "low_cost": Factor("cost_attendance", False, "lower cost", "Cost ${:,.0f}", "lower"),
    "low_tuition": Factor("tuition_in_state", False, "lower in-state tuition", "Tuition ${:,.0f}", "lower"),
    "high_earnings": Factor("median_earnings_10yr", True, "higher earnings", "Earnings ${:,.0f}", "higher"),
    "high_completion": Factor("completion_rate_150", True, "higher graduation rate", "Graduation {:.0%}", "higher"),
    "high_retention": Factor("retention_rate", True, "higher retention", "Retention {:.0%}", "higher"),
    "low_debt": Factor("median_debt", False, "lower debt", "Median debt ${:,.0f}", "lower"),
    "selective": Factor("admission_rate", False, "more selective", "Admission {:.0%}", "more selective"),
    "accessible": Factor("admission_rate", True, "easier admission", "Admission {:.0%}", "easier"),
    "small": Factor("enrollment_undergrad", False, "smaller", "{:,.0f} undergraduates", "smaller"),
    "large": Factor("enrollment_undergrad", True, "larger", "{:,.0f} undergraduates", "larger"),
}
MAX_WEIGHT = 3
MAX_REASONS = 2
STRONG = 0.5  # only a figure at or above the median is described as "better than X%"


def parse_prefer(values):
    """["low_cost:2", "small"] -> [("low_cost", 2), ("small", 1)]; unknown factors dropped, weights 1-3."""
    weights = {}
    for value in values:
        name, _, weight = value.partition(":")
        if name not in FACTORS:
            continue
        weight = int(weight) if weight.isdecimal() else 1
        weights[name] = max(weights.get(name, 0), min(max(weight, 1), MAX_WEIGHT))
    return list(weights.items())


def prefer_param(name, weight):
    return f"{name}:{weight}"


@dataclass
class Ranked:
    pk: int
    score: float
    reasons: list = field(default_factory=list)


def _percentiles(rows, factor):
    """{pk: share of OTHER reporting schools this school beats (ties count half)}, reporters only."""
    values = sorted(float(row[factor.field]) for row in rows if row[factor.field] is not None)
    others = len(values) - 1
    result = {}
    for row in rows:
        if row[factor.field] is None:
            continue
        value = float(row[factor.field])
        below, above = bisect_left(values, value), len(values) - bisect_right(values, value)
        ties = len(values) - below - above - 1
        beaten = below if factor.higher_is_better else above
        result[row["pk"]] = 1.0 if others == 0 else (beaten + ties / 2) / others
    return result


def rank(schools, prefer, extra=None, extra_weight=2):
    """Order `schools` (a queryset already narrowed by the hard filters) by soft preferences.

    `prefer` is [(factor, weight)]; `extra` is {pk: (score 0-1, reason)} for one more signal.
    Returns [Ranked(pk, score, reasons)], best first.
    """
    factors = [(FACTORS[name], weight) for name, weight in prefer if name in FACTORS]
    columns = {factor.field for factor, _ in factors}
    rows = list(schools.values("pk", "name", "unitid", *columns))
    percentiles = [(factor, weight, _percentiles(rows, factor)) for factor, weight in factors]
    total = sum(weight for _, weight in factors) + (extra_weight if extra else 0)

    ranked = []
    for row in rows:
        reported, earned, reasons = 0, 0.0, []
        for factor, weight, scores in percentiles:
            if row["pk"] in scores:
                p = scores[row["pk"]]
                reported += weight
                earned += weight * p
                reasons.append((weight * p, p, factor.show(row[factor.field]), factor))
        if extra and row["pk"] in extra:
            p, text = extra[row["pk"]]
            reported += extra_weight
            earned += extra_weight * p
            reasons.append((extra_weight * p + 1, 0, text, None))  # always listed first when present
        score = 0.0 if not reported else (earned / reported) * (0.5 + 0.5 * reported / total)
        # A school with no usable figure for any requested factor can't be judged at all: it goes after every
        # school that could, even one that scored 0 by being the worst on the figures it reports.
        reasons.sort(key=lambda reason: -reason[0])
        shown = []
        for _, p, text, factor in reasons[:MAX_REASONS]:
            if factor is not None and p >= STRONG:
                text = f"{text} · {factor.word} than {round(p * 100)}% of matches"
            if text:
                shown.append(text)
        ranked.append((not reported, score, row["name"], row["unitid"], Ranked(row["pk"], round(score, 6), shown)))
    ranked.sort(key=lambda item: (item[0], -item[1], item[2], item[3]))
    return [item[4] for item in ranked]


def match_majors(keyword, limit=None):
    """[(cip_code, field name)] of bachelor's fields whose name contains `keyword`, most widely offered first.

    Filtering must use every match (pass no limit); `limit` is only for showing a few names.
    """
    keyword = " ".join(keyword.split())[:60]
    if not keyword:
        return []
    fields = (Program.objects.filter(credential_level=3, name__icontains=keyword)
              .values("cip_code", "name").annotate(schools=Count("institution", distinct=True))
              .order_by("-schools", "cip_code"))
    if limit is not None:
        fields = fields[:limit]
    return [(row["cip_code"], row["name"].rstrip(".")) for row in fields]
