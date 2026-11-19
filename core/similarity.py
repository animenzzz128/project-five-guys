"""Find colleges similar to a given one (#16).  Owner: B.

Every comparison uses College Scorecard fields only, and no LLM is involved.

How it works
------------
1. `build_profiles()` runs from `seed` and `import_scorecard`, never per request.
   For each school it stores an 18-number pgvector (`SimilarityProfile.vector`):
   five numeric features as z-scores, then one-hot ownership and region.  A
   missing value is written as 0 so pgvector can index the row, and the
   `present` bitmask records which features were really reported.
2. `similar_institutions()` asks Postgres for the nearest `CANDIDATE_POOL`
   vectors by L2 distance (pgvector's `<->`), then re-ranks that pool in Python
   using ONLY the features both schools report.  The pgvector distance still
   sees the 0 placeholders, so it is only a pre-filter: the pool is kept large
   enough that the final top 10 almost always matches an exhaustive scan.  A missing value is left out,
   never treated as 0 or as the average.  Distance is the root-mean-square gap
   over the shared features, so a pair is not rewarded for sharing fewer of them.
3. Reasons come from the shared features with the smallest gaps, shown with the
   real figures for both schools.

On SQLite (local dev without Postgres) step 2 ranks every profile in Python,
i.e. the exhaustive scan.
"""

import math
from dataclasses import dataclass, field

from django.db import connection, transaction
from django.db.models import Q
from pgvector.django import L2Distance

from .models import Institution, SimilarityProfile

# Numeric features: (bit, model field, transform, reason label, (number format, unit)).
NUMERIC = (
    (0, "enrollment_undergrad", math.log1p, "Similar size", ("{:,.0f}", " undergraduates")),
    (1, "cost_attendance", None, "Similar cost", ("${:,.0f}", " a year")),
    (2, "admission_rate", None, "Similar admission rate", ("{:.0%}", " admitted")),
    (3, "completion_rate_150", None, "Similar graduation rate", ("{:.0%}", " graduate")),
    (4, "median_earnings_10yr", None, "Similar earnings", ("${:,.0f}", " median earnings after 10 years")),
)
OWNERSHIP_BIT, REGION_BIT = 5, 6
OWNERSHIP_CODES = (1, 2, 3)
REGION_CODES = tuple(range(10))
REGION_NAMES = {
    0: "U.S. service schools", 1: "New England", 2: "Mid East", 3: "Great Lakes", 4: "Plains",
    5: "Southeast", 6: "Southwest", 7: "Rocky Mountains", 8: "Far West", 9: "Outlying areas",
}
DIMENSIONS = len(NUMERIC) + len(OWNERSHIP_CODES) + len(REGION_CODES)  # 18
ONE_HOT = 1 / math.sqrt(2)  # a category mismatch then costs exactly 1.0 of L2 distance

MIN_NUMERIC = 3  # a school (and each pair) needs at least 3 shared numeric features
# Nearest vectors fetched from pgvector before exact re-ranking.  On the November
# 2026 snapshot (2,321 comparable schools), 150 random lookups vs an exhaustive
# scan: pool 200 -> 22 top-10 lists differ, 500 -> 5, 1000 -> 1 (about 26 ms).
CANDIDATE_POOL = 1000
CLOSE_GAP = 0.5  # a feature counts as "similar" within half a standard deviation
CATEGORY_GAP = 0.3  # where a matching category sorts among the numeric reasons
MAX_REASONS, MIN_REASONS = 3, 2


class NotComparable(Exception):
    """The source school reports too few features to compare fairly."""


@dataclass
class SimilarResult:
    institution: Institution
    distance: float
    shared: int
    reasons: list = field(default_factory=list)  # [{"label": ..., "detail": ...}]


def _number(value):
    return None if value is None else float(value)


def _features(row, stats):
    """Return (vector, present bitmask) for one institution's values."""
    vector, present = [0.0] * DIMENSIONS, 0
    for bit, name, transform, _, _ in NUMERIC:
        value = _number(row[name])
        if value is None:
            continue
        if transform:
            value = transform(value)
        mean, std = stats[name]
        vector[bit] = (value - mean) / std
        present |= 1 << bit
    offset = len(NUMERIC)
    if row["ownership"] in OWNERSHIP_CODES:
        vector[offset + OWNERSHIP_CODES.index(row["ownership"])] = ONE_HOT
        present |= 1 << OWNERSHIP_BIT
    offset += len(OWNERSHIP_CODES)
    if row["region"] in REGION_CODES:
        vector[offset + row["region"]] = ONE_HOT
        present |= 1 << REGION_BIT
    return vector, present


def _stats(rows):
    """Mean and standard deviation of each numeric feature over reported values."""
    stats = {}
    for _, name, transform, _, _ in NUMERIC:
        values = [_number(row[name]) for row in rows if row[name] is not None]
        values = [transform(v) if transform else v for v in values]
        if not values:
            stats[name] = (0.0, 1.0)
            continue
        mean = sum(values) / len(values)
        std = math.sqrt(sum((v - mean) ** 2 for v in values) / len(values))
        stats[name] = (mean, std or 1.0)
    return stats


def _numeric_count(present):
    return sum(1 for bit, *_ in NUMERIC if present & (1 << bit))


@transaction.atomic
def build_profiles():
    """(Re)compute every school's vector.  Safe to run any number of times.

    Demo rows and real federal rows are normalized separately, because they are
    never compared with each other.
    """
    names = ["pk", "data_release", "ownership", "region"] + [name for _, name, *_ in NUMERIC]
    rows = list(Institution.objects.values(*names))
    groups = {}
    for row in rows:
        groups.setdefault(row["data_release"] == Institution.SAMPLE, []).append(row)

    profiles = []
    for group in groups.values():
        stats = _stats(group)
        for row in group:
            vector, present = _features(row, stats)
            if _numeric_count(present) >= MIN_NUMERIC:
                profiles.append(SimilarityProfile(institution_id=row["pk"], vector=vector, present=present))

    keep = [profile.institution_id for profile in profiles]
    SimilarityProfile.objects.exclude(institution_id__in=keep).delete()
    SimilarityProfile.objects.bulk_create(
        profiles, batch_size=500, update_conflicts=True,
        unique_fields=["institution"], update_fields=["vector", "present", "computed_at"],
    )
    return len(profiles)


def _gaps(source, other):
    """Per-feature gap over the features both profiles report: {bit: gap}."""
    shared = source.present & other.present
    gaps = {}
    for bit, *_ in NUMERIC:
        if shared & (1 << bit):
            gaps[bit] = abs(source.vector[bit] - other.vector[bit])
    for bit, start, size in ((OWNERSHIP_BIT, len(NUMERIC), len(OWNERSHIP_CODES)),
                             (REGION_BIT, len(NUMERIC) + len(OWNERSHIP_CODES), len(REGION_CODES))):
        if shared & (1 << bit):
            same = list(source.vector[start:start + size]) == list(other.vector[start:start + size])
            gaps[bit] = 0.0 if same else 1.0
    return gaps


def _reasons(source_school, school, gaps):
    candidates = []
    for bit, name, _, label, figure in NUMERIC:
        if bit in gaps:
            number, unit = figure
            here, there = _number(getattr(school, name)), _number(getattr(source_school, name))
            detail = f"{number.format(here)}{unit} ({source_school.name}: {number.format(there)})"
            candidates.append((gaps[bit], label, detail))
    if gaps.get(OWNERSHIP_BIT) == 0.0:
        candidates.append((CATEGORY_GAP, f"Also {school.get_ownership_display().lower()}", "Same type of school"))
    if gaps.get(REGION_BIT) == 0.0:
        candidates.append((CATEGORY_GAP, "Same region", REGION_NAMES[school.region]))
    candidates.sort(key=lambda reason: reason[0])
    close = [reason for reason in candidates if reason[0] <= CLOSE_GAP][:MAX_REASONS]
    if len(close) < MIN_REASONS:
        close = candidates[:MIN_REASONS]
    return [{"label": label, "detail": detail} for _, label, detail in close]


def similar_institutions(unitid, k=10, exclude_ids=frozenset(), filters=None):
    """Up to `k` schools most like `unitid`, closest first, never including it.

    `exclude_ids` are unitids to leave out (e.g. schools already on a shortlist).
    `filters` is an optional Q over Institution fields that narrows candidates.
    Raises Institution.DoesNotExist for an unknown unitid and NotComparable when
    the school reports fewer than MIN_NUMERIC numeric features.
    """
    school = Institution.objects.get(unitid=unitid)
    try:
        source = school.similarity_profile
    except SimilarityProfile.DoesNotExist:
        raise NotComparable(school) from None

    pool = SimilarityProfile.objects.exclude(pk=school.pk).select_related("institution")
    same_dataset = Q(institution__data_release=Institution.SAMPLE)
    pool = pool.filter(same_dataset) if school.is_sample else pool.exclude(same_dataset)
    if exclude_ids:
        pool = pool.exclude(institution__unitid__in=exclude_ids)
    if filters is not None:
        pool = pool.filter(institution__in=Institution.objects.filter(filters))
    if connection.vendor == "postgresql":
        pool = pool.order_by(L2Distance("vector", source.vector))[:CANDIDATE_POOL]

    results = []
    for profile in pool:
        gaps = _gaps(source, profile)
        numeric = sum(1 for bit, *_ in NUMERIC if bit in gaps)
        if numeric < MIN_NUMERIC:
            continue
        distance = math.sqrt(sum(gap ** 2 for gap in gaps.values()) / len(gaps))
        results.append((SimilarResult(profile.institution, distance, len(gaps)), gaps))
    results.sort(key=lambda pair: (pair[0].distance, pair[0].institution.name, pair[0].institution.unitid))
    top = []
    for result, gaps in results[:k]:
        result.reasons = _reasons(school, result.institution, gaps)
        top.append(result)
    return top
