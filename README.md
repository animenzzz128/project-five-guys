# Admit Compass (team noble-shape, MGT 656)

Staging: https://noble-shape-staging.onrender.com (free plan; first request after idle takes ~1 min)

Build a college shortlist from federal College Scorecard data, then ask
questions about it. Django + PostgreSQL, deployed on Render with a Neon
database.

## Run it locally (3 steps)

```sh
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env && python manage.py migrate && python manage.py runserver
```

Open http://127.0.0.1:8000/ . With `DEBUG=True` and no `DATABASE_URL`, the app
uses a local SQLite file. To use Postgres, set `DATABASE_URL` in `.env`.

Before opening a PR, run what CI runs:

```sh
ruff check . && python manage.py test
```

## Who owns what

| Folder | Owner | What goes there |
| --- | --- | --- |
| `config/`, `requirements*.txt`, `build.sh`, `render.yaml`, `.github/` | A | settings, dependencies, deploy, CI |
| `accounts/`, `templates/`, `static/` | B | sign up / log in / log out, base layout |
| `abtest/` | C | `/fd986fa` A/B page and `/fd986fa/stats` |
| `core/` | D | models, `seed` management command |
| `docs/` | E | `docs/mgt656/` reports, backlog notes |

All three apps are already in `INSTALLED_APPS` and their `urls.py` files are
already included from `config/urls.py`, so you only edit files inside your own
app. Need a new dependency or setting? Open a PR and ask A to review.

Rules: work on a branch, PR says `Closes #<issue>`, a teammate reviews before
merge, each app makes its own migrations.

Deployment: see [DEPLOY.md](DEPLOY.md).

## Undergraduate program catalog

After `python manage.py migrate`, run `python manage.py import_scorecard` in the
target environment to load the bundled nationwide snapshot. Open `/programs/` and
search by school or field. The catalog import runs explicitly, independently of
the demo seed; a fresh deployment needs the import once. Reruns upsert schools
on UNITID and federal fields on school, four-digit CIP and credential level.
Existing school IDs, student shortlists, and manually maintained catalog links
on federal rows survive a repeated import.

The source is the U.S. Department of Education's [College Scorecard](https://collegescorecard.ed.gov/data/).
The institution release is [November 2, 2026](https://ed-public-download.scorecard.network/downloads/Most-Recent-Cohorts-Institution_11022026.zip);
the Field of Study release is [October 15, 2026](https://ed-public-download.scorecard.network/downloads/Most-Recent-Cohorts-Field-of-Study_10152026.zip).
These are release dates; measurements in the most-recent cohorts files can come from different years.
Redistributed extracts are attributed to the Department of Education; see the
[dataset metadata and license](https://catalog.data.gov/dataset/college-scorecard).

Scope: currently operating schools in the 50 states, DC and US territories with
a reported bachelor's field, a bachelor's offering flag or a highest/predominant
bachelor's award. Includes 2,462 schools and 67,992 federal fields. Of 70,944
bachelor's source rows (CREDLEV=3), 1,856 have no numeric UNITID and 1,096 do
not match an in-scope current institution. Institutions can qualify even when
the field file has no matching detail. Preserve leading CIP zeros. A federal
field groups degrees and is not a campus-specific BA/BS or a list of current
admissions openings.

Specific degrees are maintained separately in the same Program table, with
no federal credential level. The three catalog entries in
`core/data/cs_programs.csv` link to the Yale and Cornell CS catalogs. The bundled federal-field links are applied during the same import. To supply or
correct an official URL, edit its Catalog URL in Django Admin. When no
program URL has been verified, the public page labels the school homepage as
**College website**. School homepage URLs are never guessed to be program URLs.

Rebuild the compact CSV extracts from those two official ZIP downloads with
`python scripts/prepare_scorecard.py INSTITUTION.zip FIELD_OF_STUDY.zip core/data/scorecard_2026`.

### Verified official program links

The November 16, 2026 snapshot adds 336 matched federal rows at 27 schools from
30 configured campus directories. With the three independently verified BA/BS
entries there are 339 linked records across 28 schools, 338 distinct URLs, and
67,656 blank program URLs. These counts exclude homepage fallbacks.

To refresh, install `requirements-dev.txt` and run
`python scripts/collect_program_links.py /tmp/catalog_links.csv`. Review the diff
before replacing `core/data/scorecard_2026/catalog_links.csv`, particularly removals
if a catalog is temporarily unavailable. Add supported campus indexes, their UNITIDs,
and program-list selectors in `core/data/catalog_directories.csv`.

The collector reads public, same-host HTTPS pages, observes robots exclusions,
and checks both the official undergraduate index and the destination title.
It accepts only one matching field and one unambiguous program URL per campus
and normalized name. Separate BA/BS URLs for one federal field are ambiguous.
A missing or blocked directory produces no matches. Sites outside the configured
directories have not been scanned. Snapshot import uses the school, four-digit CIP
and credential level; no external requests are made by the application.

After schema migration, `python manage.py import_scorecard` includes the links.
For an existing nationwide catalog, `python manage.py apply_catalog_links`
refreshes only the URLs. Removed automatic matches are cleared and curator edits
are preserved.
