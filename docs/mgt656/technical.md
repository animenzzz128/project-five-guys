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
