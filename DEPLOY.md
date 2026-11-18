# Deploying (staging now, production in Sprint 2)

No passwords or keys go in this repo. Real values live only in the Render
dashboard (and in your own untracked `.env`).

## How it fits together

- **Code:** GitHub `main` branch.
- **App:** Render web service `noble-shape-staging` (free plan), defined in
  `render.yaml`. Every push to `main` redeploys it.
- **Database:** Neon Postgres project, connected through `DATABASE_URL`.
- **Build** (`build.sh`): install → `collectstatic` → `migrate` → `seed` (once
  D's seed command exists).
- **Start:** `gunicorn config.wsgi:application --bind 0.0.0.0:$PORT`.
- **Health check:** `GET /healthz` returns `{"status": "ok"}` when the app can
  reach the database, `503` otherwise.

Render's free plan has **no Shell and no pre-deploy command**, which is why
migrations and the seed run inside `build.sh`. The seed must therefore be safe
to run on every deploy. Free services sleep after 15 idle minutes; the first
request after that takes about a minute.

## Environment variables

| Name | Staging value | Where it comes from |
| --- | --- | --- |
| `DATABASE_URL` | Neon connection string (`...?sslmode=require`) | paste in Render when creating the Blueprint |
| `SECRET_KEY` | random | Render generates it (`generateValue`) |
| `DEBUG` | `False` | `render.yaml` |
| `WEB_CONCURRENCY` | `2` | `render.yaml` |
| `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` | not needed | Render's own hostname is added automatically from `RENDER_EXTERNAL_HOSTNAME`; set these only for a custom domain |
| `OPENROUTER_API_KEY` | team's OpenRouter key (secret) | Render dashboard → Environment; without it AI features fall back instead of calling the LLM |
| `OPENROUTER_MODEL` | optional, e.g. `openai/gpt-4o-mini` (the default) | Render dashboard → Environment |

Python version comes from `.python-version` (3.12).

## First-time setup (about 10 minutes)

### 1. Neon (database)

1. Sign up at https://neon.tech (GitHub login is fine).
2. Create a project, e.g. `noble-shape`, region US East. The default branch
   and database (`neondb`) are fine for staging.
3. On the project dashboard click **Connect**, keep "Pooled connection" on,
   and copy the connection string. It looks like
   `postgresql://USER:PASSWORD@ep-xxx-pooler.us-east-2.aws.neon.tech/neondb?sslmode=require`.
   Do not paste it in chat or in the repo.

### 2. Render (app)

1. Sign up at https://render.com with GitHub and allow it to see this repo.
2. **New → Blueprint**, pick this repo, branch `main`.
3. Render reads `render.yaml` and asks for `DATABASE_URL`: paste the Neon
   string. Click **Apply**.
4. Wait for the first deploy (3–5 minutes). The log should end with
   `Your service is live`.
5. The URL is shown at the top of the service page, e.g.
   `https://noble-shape-staging.onrender.com`. Post it to the team.

### 3. Check it

```sh
curl https://<staging-host>/healthz        # {"status": "ok", "database": "postgresql"}
```

Also open `/admin/login/` in a private window: the page should be styled
(static files work). Logging in with a wrong password should show "Please
enter a correct username..." rather than a 403 (CSRF works).

## Common problems

| Symptom | Cause / fix |
| --- | --- |
| Build fails: `DATABASE_URL must be set` | env var missing in Render → Environment |
| `/healthz` returns 503 | Neon string wrong, or Neon project suspended; check Render logs |
| 400 Bad Request | a custom domain is not in `ALLOWED_HOSTS` |
| 403 on form POST | a custom domain is not in `CSRF_TRUSTED_ORIGINS` (needs `https://`) |
| Page has no CSS | `collectstatic` failed in the build log |
| Migrations conflict | two people made migrations in the same app; regenerate on top of `main` |

## Production (Sprint 2)

| | Staging | Production |
| --- | --- | --- |
| URL | https://noble-shape-staging.onrender.com | https://noble-shape.onrender.com |
| Render service | `noble-shape-staging` (Blueprint, Oregon) | `noble-shape` (created in the dashboard, Ohio) |
| Neon branch / database | `staging` / `neondb` | `production` / `noble_prod` (no expiry) |
| Deploys | automatically, after CI passes on `main` | **manually**: Render → `noble-shape` → Manual Deploy |

Production has its own `SECRET_KEY`; the grader passwords (`SEED_*`) are the
same as staging so the grader notes work on both.

**Promote to production:** check the change on staging, then Manual Deploy →
"Deploy latest commit" on `noble-shape`. **Roll back:** Deploys → pick the last
good deploy → Rollback (release `v0.1.0` = Sprint 1 baseline, commit `b8a3c65`).
Rolling back code does not undo migrations: before a risky migration, create a
Neon branch from `production` as a restore point.

Before the Sprint 4 A/B bot run, delete our own test impressions and clicks on
production.

## Tooling

- **CI** (`.github/workflows/ci.yml`): `test` job (ruff, Django checks,
  migrations check, unit tests) and `e2e + accessibility` job (Playwright +
  axe-core, `e2e/tests.py`). `main` is protected: both must pass and one
  teammate must approve before merging.
- **Dependabot** (`.github/dependabot.yml`): weekly grouped update PRs for pip
  and GitHub Actions, plus security updates.
- **CodeQL**: GitHub code scanning (default setup) on every PR.
- **Sentry**: error tracking, enabled only when `SENTRY_DSN` is set. In Render
  set `SENTRY_DSN` and `SENTRY_ENVIRONMENT` (`staging` / `production`) on each
  service.

Run the browser tests locally:

```sh
pip install -r requirements-dev.txt
python -m playwright install chromium
DEBUG=True python manage.py test --tag e2e
```
