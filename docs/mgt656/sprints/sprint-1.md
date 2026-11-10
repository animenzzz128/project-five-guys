# Sprint 1 — walking skeleton

**Team:** noble-shape · **Dates:** Nov 2 – Nov 11, 2026 · **App:** Admit Compass

## Goal

Get one thin slice of the whole pipeline working end to end — repo, Django app,
Postgres, accounts, the A/B page, seed data, CI and a public staging deploy —
before any product feature is built. Nothing in this sprint is meant to be the
finished product; it is meant to prove the pipeline.

## What shipped

| Area | Owner | Issue | Evidence |
| --- | --- | --- | --- |
| Repo skeleton, settings from environment, Render + Neon deploy, CI | A (animenzzz128) | — | [`d73d149`](https://github.com/animenzzz128/project-five-guys/commit/d73d149) pushed directly to `main` |
| Accounts (sign up / log in / log out) + `base.html` layout | B (Yida1201) | [#1](https://github.com/animenzzz128/project-five-guys/issues/1) | [#2](https://github.com/animenzzz128/project-five-guys/pull/2) |
| Landing page with AI advisor and roadmap | B (Yida1201) | [#17](https://github.com/animenzzz128/project-five-guys/issues/17) | [#19](https://github.com/animenzzz128/project-five-guys/pull/19) |
| Dashboard after log-in | B (Yida1201) | [#20](https://github.com/animenzzz128/project-five-guys/issues/20) | [#21](https://github.com/animenzzz128/project-five-guys/pull/21) |
| A/B page at `/fd986fa` and `/fd986fa/stats` | C (haloikuy) | [#5](https://github.com/animenzzz128/project-five-guys/issues/5) | [#6](https://github.com/animenzzz128/project-five-guys/pull/6) |
| `core` models + idempotent `seed` command | D (LuanfengBest) | [#14](https://github.com/animenzzz128/project-five-guys/issues/14) | [#4](https://github.com/animenzzz128/project-five-guys/pull/4) |
| Backlog, GitHub Project with four iterations, `docs/mgt656/` | E (trippleway) | — | [#13](https://github.com/animenzzz128/project-five-guys/pull/13) |

## What works on staging

Staging: https://noble-shape-staging.onrender.com

- [x] `/healthz` responds with `{"status": "ok", "database": "postgresql"}`.
- [x] Student account login is verified on staging.
- [x] `/fd986fa` and `/fd986fa/stats` are reachable.
- [x] Refreshing the A/B page preserves the assigned variant.
- [x] Repeating the same A/B click does not add a second click; the stats remained unchanged after two repeat clicks.
- [x] The A/B page has no horizontal scrolling at a 375 px-wide viewport.
- [x] Deployment Seed Command Verification: `python manage.py seed` is verified on the staging deployment.
- [x] CI is green for the latest `main` commits.

All listed Sprint 1 verification checks now have evidence.

## Working with our agents

Two concrete review findings guided the final implementation. In [#4](https://github.com/animenzzz128/project-five-guys/pull/4), the initial AI-assisted seed command placed the grading-account password in the public repository. Review moved that value to an environment variable and added a test so it cannot be reintroduced. In [#6](https://github.com/animenzzz128/project-five-guys/pull/6), a test initially mocked all of `secrets.choice`, which also interfered with Django session-key generation. The fix restricted the mock to the single A/B-assignment call. These reviews kept secrets out of source control and made the A/B test deterministic without breaking session behavior.

## Backlog changes for Sprint 2

The Project now carries fourteen user stories across four dated iterations. The
completed Sprint 1 items [#14](https://github.com/animenzzz128/project-five-guys/issues/14),
[#17](https://github.com/animenzzz128/project-five-guys/issues/17), and
[#20](https://github.com/animenzzz128/project-five-guys/issues/20) are on the
Project and assigned to the Sprint 1 iteration.

- Sprint 2: [#7](https://github.com/animenzzz128/project-five-guys/issues/7), [#8](https://github.com/animenzzz128/project-five-guys/issues/8), and [#16](https://github.com/animenzzz128/project-five-guys/issues/16)
- Sprint 3: [#9](https://github.com/animenzzz128/project-five-guys/issues/9) and [#10](https://github.com/animenzzz128/project-five-guys/issues/10)
- Sprint 4: [#11](https://github.com/animenzzz128/project-five-guys/issues/11), [#12](https://github.com/animenzzz128/project-five-guys/issues/12), [#15](https://github.com/animenzzz128/project-five-guys/issues/15), and [#18](https://github.com/animenzzz128/project-five-guys/issues/18)

The committed Sprint 2 items are #7, #8, and #16; the remaining items stay planned in
their later iterations so the team can reprioritize them if validation changes.
