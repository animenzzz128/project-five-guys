# Sprint 1 — walking skeleton

**Team:** noble-shape · **Dates:** Nov 2 – Nov 11, 2026 · **App:** Admit Compass

## Goal

Get one thin slice of the whole pipeline working end to end — repo, Django app,
Postgres, accounts, the A/B page, seed data, CI and a public staging deploy —
before any product feature is built. Nothing in this sprint is meant to be the
finished product; it is meant to prove the pipeline.

## What shipped

<!-- TODO(E) on merge day: replace each row's PR number and tick the box once it is merged. -->

| Area | Owner | Issue | PR |
| --- | --- | --- | --- |
| Repo skeleton, settings from env, Render + Neon deploy, CI | A (animenzzz128) | — | TODO |
| Accounts (sign up / log in / log out) + `base.html` layout | B (Yida1201) | [#1](https://github.com/animenzzz128/project-five-guys/issues/1) | [#2](https://github.com/animenzzz128/project-five-guys/pull/2) |
| A/B page at `/fd986fa` and `/fd986fa/stats` | C (haloikuy) | [#5](https://github.com/animenzzz128/project-five-guys/issues/5) | [#6](https://github.com/animenzzz128/project-five-guys/pull/6) |
| `core` models + idempotent `seed` command | D (LuanfengBest) | — | [#4](https://github.com/animenzzz128/project-five-guys/pull/4) |
| Backlog, GitHub Project with four iterations, `docs/mgt656/` | E (trippleway) | — | TODO |

## What works on staging

Staging: https://noble-shape-staging.onrender.com

<!-- TODO(E) on merge day: tick these off after walking the list on staging yourself. -->

- [ ] Home page loads in a private window
- [ ] A grader account from `seed` can log in, and log out returns to the logged-out state
- [ ] No horizontal scroll at 375px
- [ ] `/fd986fa` loads logged out and has exactly one `<button id="abtest">` reading `kudos` or `thanks`
- [ ] Ten reloads keep the same variant and add one impression; two clicks add one click
- [ ] `/fd986fa/stats` returns JSON whose `preferred` is the higher click-rate variant
- [ ] `seed` runs twice on an empty database with no errors and no duplicates

## Working with our agents

<!-- TODO(E) on merge day: replace this paragraph with one concrete thing from this sprint. -->

The useful lesson this sprint was that the agents are only as good as the
acceptance criteria they are handed. The first stories we wrote were one-line
descriptions, and the generated code looked plausible but missed the parts
nobody had written down — `?next=` redirect safety on login, and counting an
impression again after the A/B form posted back. We rewrote the backlog so every
story's acceptance criteria are checkable sentences naming routes, status codes
and the exact counting behaviour, and we review against that list rather than
against the diff. The split of one app folder per person was the other thing
that held: `migrations` are made per app, so no two agents produced conflicting
migration files.

## Backlog changes for Sprint 2

The board now carries eight `user story` issues across four iterations
(Sprint 1: Nov 2–11, Sprint 2: Nov 12–18, Sprint 3: Nov 19–Dec 2,
Sprint 4: Dec 3–11).

Committed to Sprint 2:

- [#7 Search and filter colleges from College Scorecard data](https://github.com/animenzzz128/project-five-guys/issues/7)
- [#8 Add and remove colleges on my shortlist](https://github.com/animenzzz128/project-five-guys/issues/8)

Planned later: #9 and #10 (compare, and the AI question feature) in Sprint 3;
#11 and #12 (shared read-only link, saved preferences) in Sprint 4. Anything
unfinished from Sprint 1 moves forward rather than being deleted.
