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

Add a second service to `render.yaml` (e.g. `noble-shape`) with its own Neon
database (a separate Neon project or branch), and decide how to promote
(manual deploy, or `autoDeployTrigger: checksPass` on a `production` branch).
