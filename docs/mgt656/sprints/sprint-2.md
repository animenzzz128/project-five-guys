# Sprint 2 — discover, save, and explore colleges

**Team:** noble-shape · **Dates:** Nov 12 – Nov 18, 2026 · **App:** Admit Compass

## Goal

Ship the first three connected steps of the student journey on top of the
Sprint 1 skeleton: discover colleges in the federal data, save the ones that
matter to a private shortlist, and use a saved school to surface comparable
alternatives. Sprint 1 proved the pipeline; Sprint 2 is the first sprint that
puts product value in front of a user.

## What shipped

| Area | Owner | Issue | Pull request | Status |
| --- | --- | --- | --- | --- |
| Search and filter colleges | D (LuanfengBest) | [#7](https://github.com/animenzzz128/project-five-guys/issues/7) | [#26](https://github.com/animenzzz128/project-five-guys/pull/26) | In review |
| Private shortlist, add and remove | D (LuanfengBest) | [#8](https://github.com/animenzzz128/project-five-guys/issues/8) | [#27](https://github.com/animenzzz128/project-five-guys/pull/27) | In review |
| Similar colleges with pgvector | B (Yida1201) | [#16](https://github.com/animenzzz128/project-five-guys/issues/16) | [#32](https://github.com/animenzzz128/project-five-guys/pull/32) | In review |
| Nationwide program catalog | D (LuanfengBest) | [#23](https://github.com/animenzzz128/project-five-guys/issues/23) | [#24](https://github.com/animenzzz128/project-five-guys/pull/24) | In review |
| Federal region data for comparisons | D (LuanfengBest) | — | [#28](https://github.com/animenzzz128/project-five-guys/pull/28) | In review |
| E2E and accessibility CI, Sentry, Dependabot | A (animenzzz128) | — | [#30](https://github.com/animenzzz128/project-five-guys/pull/30) | In review |
| Sprint 2 user stories and acceptance criteria | E (trippleway) | [#7](https://github.com/animenzzz128/project-five-guys/issues/7), [#8](https://github.com/animenzzz128/project-five-guys/issues/8), [#16](https://github.com/animenzzz128/project-five-guys/issues/16) | — | Done |

All three committed stories were specified with testable acceptance criteria and
implemented, and every feature went through a pull request with CI. At the time
of writing, the feature branches are under review rather than on `main`, so the
three issues stay open until their PRs merge and the acceptance criteria are
checked against the deployed app.

## What works on staging

Staging: https://noble-shape-staging.onrender.com

- [x] Sprint 1 surface is live: accounts, landing page, dashboard, `/healthz`,
      and the A/B page at `/fd986fa` with `/fd986fa/stats`.
- [x] `python manage.py seed` is idempotent and verified on staging.
- [x] CI is green on `main`.
- [ ] Sprint 2 features are not on staging yet; they land as #26, #27 and #32
      merge.

## Working with our agents

Our clearest lesson this sprint was about where an agent's output belongs, not
about its quality. The Sprint 2 requirements were drafted with an agent and
committed to `docs/mgt656/sprints/sprint-2.md` in [#25](https://github.com/animenzzz128/project-five-guys/pull/25).
The document itself was sound, but that path is the sprint report, and review
caught that we had put a requirements document where the report has to live.
The acceptance criteria already existed verbatim in issues #7, #8 and #16, so
the document was also duplicating the backlog. We changed two things: the
specification stays in the issue it governs, where the engineer and the reviewer
actually read it, and before an agent writes a file we now say which artifact
the course requires at that path. Fluent output is not the thing to check; the
thing to check is whether it is the artifact that was asked for.

## Backlog changes for Sprint 3

- **Committed for Sprint 3:** [#9](https://github.com/animenzzz128/project-five-guys/issues/9)
  (compare shortlisted colleges side by side) and
  [#10](https://github.com/animenzzz128/project-five-guys/issues/10)
  (ask questions in plain language about my shortlist). #10 is the AI feature
  and is the sprint's main risk, so it goes first.
- **Carried into Sprint 3 if they do not merge tonight:** #7, #8 and #16.
  They are code-complete and in review, so the carry-over is review throughput,
  not unfinished work. Our first change for Sprint 3 is to review and merge
  daily instead of batching merges at the end of the sprint.
- **Opened during the sprint:** [#23](https://github.com/animenzzz128/project-five-guys/issues/23)
  (nationwide program catalog) and
  [#29](https://github.com/animenzzz128/project-five-guys/issues/29)
  (landing-page colour-contrast failures, found by the new accessibility CI).
- **Unchanged in Sprint 4:** #11, #12, #15 and #18.
