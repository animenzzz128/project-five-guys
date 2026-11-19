# Technical challenge and testing

Admit Compass is a Django 5.2 app on PostgreSQL (Neon) deployed to Render, with
separate staging and production services and databases (`DEPLOY.md`). This file
lists each technical-challenge item we built, where its code lives, the pull
requests that delivered it and how to see it working, then our testing strategy.

| # | Item (course category) | Main pull requests | See it |
| --- | --- | --- | --- |
| 1 | CI: tests and linting on every pull request, merge blocked on failure (Delivery) | [#30](https://github.com/animenzzz128/project-five-guys/pull/30) | the checks on any pull request |
| 2 | CD: `main` deploys staging automatically, production is promoted deliberately (Delivery) | [#30](https://github.com/animenzzz128/project-five-guys/pull/30) | Render dashboard, `DEPLOY.md` |
| 3 | End-to-end browser tests (Playwright) and accessibility checks in CI (Frontend and quality) | [#30](https://github.com/animenzzz128/project-five-guys/pull/30) | the `e2e + accessibility` check |
| 4 | Error tracking (Sentry) and a health-check endpoint (Delivery) | [#30](https://github.com/animenzzz128/project-five-guys/pull/30) | `/healthz` |
| 5 | Importing external data: the College Scorecard snapshot and program catalog (Backend) | [#24](https://github.com/animenzzz128/project-five-guys/pull/24), [#28](https://github.com/animenzzz128/project-five-guys/pull/28) | `/programs/`, `/colleges/` |
| 6 | Retrieval over our own data with pgvector: "Find similar" (AI) | [#32](https://github.com/animenzzz128/project-five-guys/pull/32) | any college → **Find similar** |
| 7 | Structured LLM output that drives app behavior: one-sentence search (AI) | [#39](https://github.com/animenzzz128/project-five-guys/pull/39), [#45](https://github.com/animenzzz128/project-five-guys/pull/45), [#46](https://github.com/animenzzz128/project-five-guys/pull/46) | `/colleges/` while logged in |

Planned: an evaluation set run like tests ([#44](https://github.com/animenzzz128/project-five-guys/issues/44))
and per-user AI usage limits ([#49](https://github.com/animenzzz128/project-five-guys/issues/49)).

## 1. CI: every pull request is tested and linted

**What it is.** `.github/workflows/ci.yml` runs on every pull request and on
every push to `main`, against a real PostgreSQL 16 service with the `vector`
extension (`pgvector/pgvector:pg16`), with `DEBUG=False` like production. The
`test` job runs `ruff check .`, `manage.py check --deploy --fail-level ERROR`,
`makemigrations --check --dry-run` and the unit and integration tests; the
`e2e + accessibility` job is described in item 3. `main` is protected: both
jobs must pass and a teammate must approve before a pull request can merge.
GitHub CodeQL scans every pull request, and Dependabot (`.github/dependabot.yml`)
opens weekly grouped update pull requests for pip and GitHub Actions, which go
through the same checks. `.github/workflows/catalog-scripts.yml` tests the
offline catalog collectors separately (item 5).

**See it.** Any pull request's **Checks** tab; a red check disables **Merge**.

## 2. CD: staging follows `main`, production is promoted on purpose

**What it is.** `render.yaml` defines the staging service with
`autoDeployTrigger: checksPass`: after CI passes on `main`, Render builds and
deploys staging. `build.sh` installs dependencies, collects static files,
applies migrations and runs `seed` (idempotent: grader accounts and demo data).
Production (`noble-shape`) is a separate Render service with its own Neon
database branch and is deployed only by **Manual Deploy**, after the change has
been checked on staging; rollback is Render's **Rollback** to an earlier deploy
(the Sprint 1 baseline is release `v0.1.0`). Configuration and secrets are
environment variables only (`.env.example`, `DEPLOY.md`); gunicorn binds to
`$PORT` and logs go to stdout.

**See it.** Merge to `main` and watch staging redeploy once CI is green; the
promote and rollback steps are in `DEPLOY.md` → "Production".

## 3. End-to-end browser tests and accessibility checks in CI

**What it is.** `e2e/tests.py` starts a live Django server and drives headless
Chromium with Playwright (tag `e2e`, run in its own CI job). Browser flows: the
A/B page keeps a visitor's variant and counts a click once; two visitors count
two impressions; no horizontal scroll at phone width. Accessibility: every
public page (home, login, sign-up, A/B page, `/colleges/`, a college, "Find
similar") is checked with axe-core; any **critical** or **serious** violation
fails the build. Known existing problems are listed by exact page, rule and
element in `KNOWN_ISSUES` with an issue each ([#29](https://github.com/animenzzz128/project-five-guys/issues/29)),
so the list can only shrink and anything new still fails.

**See it.** The `e2e + accessibility` check on any pull request; locally
`python -m playwright install chromium` then `DEBUG=True python manage.py test --tag e2e`.

## 4. Error tracking and health check

**What it is.** `/healthz` (`core/views.py`) runs `SELECT 1` and returns
`{"status": "ok", "database": "postgresql"}`, or HTTP 503 when the database is
unreachable; Render uses it as the service health check, and it is exempt from
the HTTPS redirect because Render probes over plain HTTP. Sentry
(`config/settings.py`, `config/sentry.py`) is on only when `SENTRY_DSN` is set,
so laptops, CI and tests never send events; it is turned on per Render service
by setting `SENTRY_DSN` and `SENTRY_ENVIRONMENT` (`staging` / `production`). Every event, performance transaction and
breadcrumb goes through `scrub_event` / `scrub_breadcrumb`, which drop request
bodies, query strings, headers, cookies and frame variables and replace
anything that looks like an email with `[email]`.

**See it.** https://noble-shape-staging.onrender.com/healthz; errors appear in
the team's Sentry project tagged with the environment.

## 5. Importing external data: College Scorecard and the program catalog

**What it is.** The app's schools and fields of study come from the U.S.
Department of Education's College Scorecard, not from an LLM. A pinned snapshot
is committed in `core/data/scorecard_2026/` (2,462 bachelor's-granting
institutions and 67,992 federal fields of study), prepared by
`scripts/prepare_scorecard.py`. `python manage.py import_scorecard` loads it in
one transaction: institutions upserted by federal UNITID, fields of study keyed
by school + four-digit CIP code + credential level, then
`apply_catalog_links` (reviewed official catalog links, applied without network
requests and without overwriting links an editor changed), `import_programs`
(specific BA/BS degree records) and `build_profiles()` for item 6. Missing
federal values import as NULL, never 0. `scripts/collect_program_links.py` and
`scripts/scan_school_catalogs.py` discover official catalog links offline; their
output is reviewed and committed, never fetched at deploy time.
`/programs/` searches the catalog and links to the official program page when
one is verified, otherwise to the college homepage, labelled differently.

**Status.** The snapshot is loaded on staging and production (the import takes
about 7 seconds locally). Documenting how it is loaded on Render, removing stale
rows on re-import and `/programs/` search speed are
[#47](https://github.com/animenzzz128/project-five-guys/issues/47) (Sprint 3).

**See it.** On staging or production, `/colleges/` shows "College Scorecard"
with 2,462 schools, `/colleges/?major=computer%20science` keeps the 826 that
offer a computer science bachelor's field, and `/programs/?q=nursing` lists
federal fields with official catalog links.

### Data notes: the inputs to "Find similar"

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

## 6. Find similar colleges (#16): retrieval over our own data with pgvector

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

## 7. One-sentence college search (#38): structured LLM output drives app behavior

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
example. Staging and production have the full 2,462-school snapshot and its
67,992 federal fields of study; a fresh local database has only the demo seed
until `python manage.py import_scorecard` is run.

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

## Testing strategy

**Levels.** About 240 automated tests run in CI on every pull request.

| Level | What it covers | Where |
| --- | --- | --- |
| Unit | Pure logic with no web request: search normalization and the LLM client, preference ranking and percentiles, similarity vectors and reasons, Sentry scrubbing | `ai/tests.py`, `ai/test_search.py`, `core/test_ranking.py`, `core/test_similarity.py`, `config/tests.py` |
| Integration (Django test client + database) | Views, forms, permissions and data rules end to end inside Django: sign-up/log-in, dashboard, A/B counting and `/stats`, filters, shortlist ownership and confirmation, imports and re-imports, the AI search view and its fallbacks | `accounts/tests.py`, `abtest/tests.py`, `core/tests.py`, `core/test_colleges.py`, `core/test_shortlists.py`, `core/test_scorecard.py`, `core/test_catalog_links.py`, `core/test_ai_filters.py`, `ai/test_views.py` |
| End to end (real browser) | Flows that need a browser and accessibility (item 3) | `e2e/tests.py` |
| Offline script tests | Catalog collectors on small inline HTML samples, network calls mocked | `script_tests/` (own workflow) |

CI runs the integration tests against PostgreSQL with pgvector, the same engine
as production; locally they can also run on SQLite.

**What we mock.**
- **The LLM.** Tests never call OpenRouter. `ai.testing.fake_ai([...])` replaces
  the client's single network function with scripted replies (dicts, raw text or
  exceptions); client tests patch `requests.post` to simulate timeouts, HTTP
  errors, errors inside a 200 response and malformed replies. A view test also
  clears `OPENROUTER_API_KEY` and asserts no request is made, so a developer's
  local key can never be used by the suite.
- **Sentry.** Off in tests (no DSN); `config/tests.py` captures what the SDK
  would send through an in-memory transport and checks each channel.
- **External websites.** Catalog collectors are tested on inline HTML samples with
  their network calls mocked; the
  Scorecard data is a committed snapshot, so no test downloads anything.

**What we don't test automatically, and why.**
- **The real model's judgement** (whether a sentence is understood well). It is
  non-deterministic and costs money; it is measured instead by an evaluation set
  run on demand ([#44](https://github.com/animenzzz128/project-five-guys/issues/44)).
- **The deployment itself.** Render builds are checked by `/healthz` and a manual
  smoke test on staging before production is promoted.
- **Visual design** beyond axe and the phone-width check: reviewed by eye on
  staging.
- **Performance with the full dataset on Render.** Tracked with the data load in
  [#47](https://github.com/animenzzz128/project-five-guys/issues/47).
