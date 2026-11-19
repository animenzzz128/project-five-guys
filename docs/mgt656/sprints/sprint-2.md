# Sprint 2 — discover, save, and explore colleges

**Team:** noble-shape · **Dates:** Nov 12 – Nov 18, 2026 · **App:** Admit Compass

## Goal

Ship the first three connected steps of the student journey on top of the
Sprint 1 skeleton: discover colleges in the federal data, save the ones that
matter to a private shortlist, and use a saved school to surface comparable
alternatives. Sprint 1 proved the pipeline; Sprint 2 is the first sprint that
puts product value in front of a user, stands up production, and starts the AI
feature.

## What shipped

| Area | Owner | Issue | Pull request | Status |
| --- | --- | --- | --- | --- |
| Search and filter colleges | D (LuanfengBest) | [#7](https://github.com/animenzzz128/project-five-guys/issues/7) | [#26](https://github.com/animenzzz128/project-five-guys/pull/26) | Merged |
| Private shortlist, add and remove | D (LuanfengBest) | [#8](https://github.com/animenzzz128/project-five-guys/issues/8) | [#27](https://github.com/animenzzz128/project-five-guys/pull/27) | Merged |
| Similar colleges with pgvector | B (Yida1201) | [#16](https://github.com/animenzzz128/project-five-guys/issues/16) | [#32](https://github.com/animenzzz128/project-five-guys/pull/32) | Merged |
| Nationwide program catalog and official links | D (LuanfengBest) | [#23](https://github.com/animenzzz128/project-five-guys/issues/23) | [#24](https://github.com/animenzzz128/project-five-guys/pull/24) | Merged |
| Verified federal region data for comparisons | D (LuanfengBest) | — | [#28](https://github.com/animenzzz128/project-five-guys/pull/28) | Merged |
| Shared OpenRouter client for AI features | C (haloikuy) | [#37](https://github.com/animenzzz128/project-five-guys/issues/37) | [#39](https://github.com/animenzzz128/project-five-guys/pull/39) | Merged |
| One-sentence search: intent recognition | C (haloikuy) | [#42](https://github.com/animenzzz128/project-five-guys/issues/42) | [#45](https://github.com/animenzzz128/project-five-guys/pull/45) | Merged |
| One-sentence search: hybrid ranking | C (haloikuy) | [#43](https://github.com/animenzzz128/project-five-guys/issues/43) | [#46](https://github.com/animenzzz128/project-five-guys/pull/46) | Merged |
| E2E and accessibility CI, Sentry, Dependabot | A (animenzzz128) | — | [#30](https://github.com/animenzzz128/project-five-guys/pull/30) | Merged |
| Production service and real Scorecard import on deploy | A (animenzzz128) | — | [#52](https://github.com/animenzzz128/project-five-guys/pull/52) | Merged |
| `technical.md`: testing strategy and technical challenge | C (haloikuy) | [#48](https://github.com/animenzzz128/project-five-guys/issues/48) | [#51](https://github.com/animenzzz128/project-five-guys/pull/51) | Merged |
| Sprint 2 user stories and acceptance criteria | E (trippleway) | [#7](https://github.com/animenzzz128/project-five-guys/issues/7), [#8](https://github.com/animenzzz128/project-five-guys/issues/8), [#16](https://github.com/animenzzz128/project-five-guys/issues/16) | — | Done |

All three committed stories (#7, #8, #16) shipped through pull requests with
review and green CI, and their issues are closed. **Production** is deployed at
https://noble-shape.onrender.com on its own Neon branch (`production` /
`noble_prod`), separate from the staging database. The **AI feature**
([#38](https://github.com/animenzzz128/project-five-guys/issues/38), one-sentence
college search) is started: the shared OpenRouter client and both halves of the
search — intent recognition and hybrid ranking — are on `main`.

## What works on staging

Staging: https://noble-shape-staging.onrender.com · Production: https://noble-shape.onrender.com

- [x] Sprint 1 surface still live: accounts, landing page, dashboard,
      `/healthz`, and the A/B page at `/fd986fa` with `/fd986fa/stats`.
- [x] `/colleges/` search and filter, the private shortlist, and "find similar"
      are on `main` and auto-deploy to staging once CI is green
      (`autoDeployTrigger: checksPass`).
- [x] One-sentence search is reachable; structured LLM output drives the query,
      with the existing filters as the fallback path.
- [x] CI on every PR: ruff, Django checks, unit tests, Playwright end-to-end
      tests and accessibility checks. CodeQL scanning on every PR.
- [x] Sentry error tracking wired for both environments.
- [ ] Loading the full federal Scorecard snapshot on staging and production is
      still open ([#47](https://github.com/animenzzz128/project-five-guys/issues/47));
      production is promoted by manual deploy, so it is pinned to the commit we
      chose rather than to every merge.

## Working with our agents

Two reviews this sprint pointed at the same weakness: agent output is fluent
enough that it reads as finished, so a reviewer who checks whether it *sounds*
right will pass it. In [#25](https://github.com/animenzzz128/project-five-guys/pull/25)
an agent-drafted requirements document was committed to
`docs/mgt656/sprints/sprint-2.md`. The document was sound, but that path is the
sprint report, and the acceptance criteria it contained already existed verbatim
in issues #7, #8 and #16, so it was both the wrong artifact and a duplicate of
the backlog. In the review of [#32](https://github.com/animenzzz128/project-five-guys/pull/32)
we found three defects the agent had no reason to consider because we never
named them: a bookmark that only inspects the first matching shortlist item, a
demo-seed function that returns early and never picks up later additions, and
similarity vectors rebuilt on every deploy whether or not the data changed.
We changed the review question. Instead of "is this correct?", we now ask "is
this the artifact that was asked for, and which cases did we never name?" The
#32 defects are filed as [#50](https://github.com/animenzzz128/project-five-guys/issues/50)
rather than left in a review thread, and specifications stay in the issue they
govern, where the engineer and the reviewer actually read them.

## Backlog changes for Sprint 3

- **Committed for Sprint 3:**
  [#9](https://github.com/animenzzz128/project-five-guys/issues/9) (compare
  shortlisted colleges side by side),
  [#10](https://github.com/animenzzz128/project-five-guys/issues/10) (ask
  questions in plain language about my shortlist), and
  [#44](https://github.com/animenzzz128/project-five-guys/issues/44) (run the
  one-sentence-search evaluation set like tests), which finishes #38.
- **Opened during the sprint and queued:**
  [#47](https://github.com/animenzzz128/project-five-guys/issues/47) (load the
  Scorecard snapshot on both environments),
  [#49](https://github.com/animenzzz128/project-five-guys/issues/49) (per-user
  daily AI usage limits),
  [#50](https://github.com/animenzzz128/project-five-guys/issues/50) (the #32
  review defects), and
  [#29](https://github.com/animenzzz128/project-five-guys/issues/29)
  (landing-page colour-contrast failures, found by the new accessibility CI).
  #47 and #49 go first: one blocks honest demos, the other caps AI spend.
- **Process change:** every Sprint 2 feature merged on the final day. We will
  review and merge daily in Sprint 3 so the sprint report describes a week of
  work rather than an evening of it.
- **Unchanged in Sprint 4:** #11, #12, #15 and #18.
