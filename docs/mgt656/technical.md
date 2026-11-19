# Similar colleges data

The nationwide import joins institutions by federal UNITID. The November 2026
institution snapshot contains 2,462 schools. These are the seven inputs for
issue #16 and their non-missing counts in that release.

| Institution field | Meaning | Schools reporting |
| --- | --- | ---: |
| `enrollment_undergrad` | Undergraduate enrollment | 2,441 |
| `cost_attendance` | Cost of attendance, dollars | 2,253 |
| `admission_rate` | Admissions fraction | 1,704 |
| `completion_rate_150` | Completion within 150% of normal time, fraction | 2,256 |
| `median_earnings_10yr` | Median earnings ten years after entry, dollars | 2,260 |
| `ownership` | Public, private nonprofit, or private for-profit | 2,462 |
| `region` | Federal Scorecard REGION category | 2,462 |

The preparation script copies REGION from the federal institution ZIP in the
[College Scorecard release](https://ed-public-download.scorecard.network/downloads/Most-Recent-Cohorts-Institution_11022026.zip).
Use region and ownership as categories. Region codes 1–8 identify geographic
regions, 0 identifies US service schools, and 9 identifies outlying areas.
Missing values import as SQL NULL. Exactly 1,550 institutions report all seven
fields in this release. Schools with partial data can still be compared on their
shared reported features. Numerical zero is a valid reported value.

After migrating, run `python manage.py import_scorecard` to populate the region
on existing institution rows. Old and demo records without a sourced region can
keep NULL. The recommendation implementation still needs to normalize numeric
features, persist vectors during import, handle missing features, and return up
to ten schools with reasons based on the data. The deployment owner coordinates
the vector extension on CI and both Neon environments.

## Find similar colleges (#16): retrieval over our own data with pgvector

**What it is.** `/colleges/<unitid>/similar/` lists up to ten schools most like
the one you picked, each with two or three plain reasons that show both
schools' real figures (for example, Harvard next to Yale shows "Similar size: 7,601 undergraduates (Yale
University: 6,758)"). Every college row and detail page links to it. No LLM is
involved.

**How it works.**

1. `core/similarity.py: build_profiles()` runs at the end of `seed` and
   `import_scorecard` (and by hand as `python manage.py build_similarity`),
   never per request. Each school gets an 18-number vector stored in
   `core.SimilarityProfile.vector` (pgvector, migration `0006` runs
   `CREATE EXTENSION IF NOT EXISTS vector`): the five numeric inputs above as
   z-scores (undergraduate size on a log scale), then one-hot ownership and
   region scaled so a category mismatch costs exactly 1.0.
2. Missing values: a missing figure is written as 0 in the vector only so
   pgvector can index the row. The `present` bitmask records which of the seven
   inputs were really reported, and everything after retrieval uses only the
   inputs **both** schools report. A school with fewer than three numeric
   inputs gets no profile and its page explains there is not enough data
   (141 of 2,462 schools in the November 2026 snapshot).
3. `similar_institutions(unitid, k=10, exclude_ids=..., filters=Q(...))` asks
   Postgres for the 1,000 nearest vectors by L2 distance (`<->`), then re-ranks
   them exactly: the root-mean-square gap over the shared inputs, skipping
   pairs that share fewer than three numeric inputs. Reasons are the shared
   inputs with the smallest gaps (within half a standard deviation where
   possible). Demo rows and federal rows are normalized and compared separately.
   On SQLite (local dev) the same re-ranking runs over every profile. Because
   the pgvector distance still sees the placeholders for missing values, the
   pool is deliberately large: in 150 random lookups it matched an exhaustive
   scan 149 times (a pool of 200 matched only 128).
4. The function is the shared engine for the AI shortlist check-up, which
   passes `exclude_ids` and `filters`.

**How to see it.** Open any college, then **Find similar**. With the federal
snapshot loaded, Yale returns Harvard, Dartmouth, Boston College, Brown and
Duke; Williams returns Amherst, Bowdoin and Bates. A lookup takes about 10 ms
locally.

**Deployment.** CI uses the `pgvector/pgvector:pg16` service image. The staging
and production Neon databases need the `vector` extension, which migration
`0006` creates (Neon supports it for the database owner role).

**Tests** (`core/test_similarity.py`): known neighbour order in a small fixture,
a missing value that is left out rather than treated as zero, the source school
never listed, the too-little-data message, `k`/`exclude_ids`/`filters`, demo and
federal rows kept apart, idempotent rebuilds, links from rows and detail pages,
and seed building profiles.

## One-sentence college search (#38): structured LLM output drives app behavior

**What it is.** Above the `/colleges/` list a logged-in student types one
sentence, in English or Chinese ("a mid-sized private school in the northeast
under $60k a year where grads earn well", "想学计算机，加州的公立大学，便宜点").
The app recognizes the intent with one LLM call, then searches our own data:
hard requirements filter the list, soft preferences rank it, each result says
why it matches, and anything we cannot search for is listed under **Can't
filter by**. The LLM never names a school or a number the student sees.

**How it works: intent recognition, then hybrid retrieval.**

1. **Client.** `ai/client.py: complete_json()` (#37, PR #39) is the one place
   the app calls an LLM: OpenRouter, server-side only, key and model from
   `OPENROUTER_API_KEY` / `OPENROUTER_MODEL`, JSON output at temperature 0,
   validated with `jsonschema`, one retry with the validation error, then
   `AIUnavailable` / `AIBadOutput` / `AILimitReached`. Logs task, model,
   latency and outcome, never the key.
2. **Intent** (`ai/schemas/search_parse.json`, prompt in `ai/search.py`):
   `intent` (search, similar, name_lookup, out_of_scope); `must` = hard
   requirements (places, public/private, explicit limits such as "under $40k");
   `prefer` = soft preferences from a fixed list of ten factors with weight 1-3
   ("cheap" → `low_cost`, "grads earn well" → `high_earnings`, "most of all" →
   weight 3); `majors` in plain English; `similar_to_name`; `unsupported`.
3. **Server-side rules** (`ai/search.py: normalize()`): regions become states
   through the fixed table in `ai/regions.py`; unknown states and states with
   no colleges in our data are dropped; numbers are clamped; a minimum above
   its maximum drops both with a note; a major is kept only if our federal
   program data has a bachelor's field by that name; "colleges like X" becomes
   `similar_to=<unitid>` only on exactly one case-insensitive name match. The
   LLM never supplies a UNITID or a CIP code. The result is saved as
   `ai.SearchInterpretation` and the student lands on
   `/colleges/?<params>&interp=<id>`; out-of-scope sentences don't search.
4. **Recall** (`core/colleges.py: _candidates()`): the must filters (#7's
   `q, state, ownership, tuition_max, size_min, size_max` plus `max_cost,
   min/max_admit, min_earnings, min_completion`), `major` (schools offering any
   matching federal bachelor's field, `core/ranking.py: match_majors()`) and
   `similar_to` (#16's `similar_institutions`), combined with AND. A school
   that doesn't report a figure never matches a filter on it.
5. **Ranking** (`core/ranking.py: rank()`, default whenever preferences exist,
   `sort=match`): for each factor a school scores its percentile among the
   candidates that report that figure; its match is the weighted mean over the
   factors it reports, times `0.5 + 0.5 × coverage`, so a missing figure is
   never treated as 0 and a school with little data can't win on the one
   figure it reports. Similarity to "X" joins as one more signal. Ties break by
   name. Each row shows its two strongest reasons built from our figures
   ("Cost $26,000 · lower than 100% of matches"). Re-ranking is left for later;
   it would take `rank()`'s output as input.
6. **When nothing matches**, the page offers the hard requirements whose
   removal alone would bring results back, with counts.
7. **Display.** Chips labelled **AI understood:** — solid for requirements,
   dashed "Prefers: …" for preferences; each removes only itself. The search
   box shows the sentence and **Can't filter by**. `{% ai_interpretation %}`
   (`ai/templatetags/ai_search.py`) reads `interp` only when it belongs to the
   viewer, so a shared link never shows someone else's sentence.

**Failure handling.** LLM unavailable or invalid twice → a plain name search
with "AI search is unavailable right now"; daily limit (Package 2) → "You've
used today's AI searches", text kept. Never a 500.

**How to see it.** Log in, open **Colleges**, type a sentence or click an
example. With only the demo seed loaded there are ten schools; run
`python manage.py import_scorecard` for the 2,462-school snapshot and its
67,992 federal fields of study.

**Tests** (`ai/tests.py`, `ai/test_search.py`, `ai/test_views.py`,
`core/test_ranking.py`, `core/test_ai_filters.py`). The LLM is always mocked:
`ai.testing.fake_ai([...])` replaces the single network call with scripted
replies (dicts, raw strings or exceptions), so CI never calls OpenRouter and
needs no key. Covered: the client (success, missing key, timeout, non-2xx,
retry, invalid twice, key never logged); normalization (must/prefer split,
regions, invalid states, clamping, min > max, majors found / not found,
`similar_to_name` found / not found / ambiguous); ranking (factor direction,
missing data, weights, coverage, ties, reasons); the view (acceptance
sentence, "cheap" ranks instead of excluding, majors, out-of-scope, empty and
too-long input, both fallbacks, the limit, logged-out redirect, another user's
`interp`, chip removal, pagination of ranked results, relax suggestions). Not
tested automatically: the real model's choices; that is what the evaluation
set (Sprint 4, `manage.py ai_eval search_parse`) is for.
