# Sprint 2 - discover, save, and explore colleges

**Team:** noble-shape

**Dates:** Nov 12 - Nov 18, 2026
**Product:** Admit Compass

## Product goal

Students should be able to move from an overwhelming catalogue of colleges to
a personal set of options they can explain and explore. Sprint 2 ships the
first three connected steps in that journey: discover schools, save the ones
that matter, and use a favourite school to uncover comparable alternatives.

This document is the product-requirements baseline for the three Sprint 2
issues. Engineering owns implementation, deployment, tests, and the feature
PRs. The product owner checks each merged feature against its acceptance
criteria before closing the corresponding issue.

---

## #7 - Search and filter colleges from College Scorecard data

### User story

**As a prospective student, I want to search and filter colleges by the
factors that matter to me, so that I can turn thousands of schools into a
short, relevant set worth investigating.**

### Narrative and pain point

A student may begin with only a vague preference such as "a public college in
Michigan that I can afford." A long alphabetical list makes that research
feel impossible: the student must open many pages and mentally compare costs,
size, and location. They need a fast way to narrow the federal data without
losing their place or having to repeat the search.

### How the product solves it

Provide a public `/colleges/` results page backed by seeded College Scorecard
institutions. The student can search part of a school name and combine state,
control, maximum in-state tuition, and undergraduate-size filters. The current
filter state stays in the URL, so the student can bookmark it, share it, use
the browser back button, and move between pages without starting again.

### Scope and acceptance criteria

- `/colleges/` lists seeded institutions 25 at a time. Every row exposes its
  name, state, public/private control, undergraduate size, and in-state tuition.
- A case-insensitive, partial-name search works; for example, `mich` finds
  `University of Michigan-Ann Arbor`.
- Students can filter by one or more states, control, maximum in-state tuition,
  and an undergraduate-size range. Multiple filters use AND logic.
- Search and filter values survive pagination and are represented in the query
  string.
- If no institutions match, the page shows a clear empty state and a link that
  clears all filters; it never returns a blank page or server error.
- The seeded-data page renders in under one second on staging and has no
  horizontal scrolling at a 320 px viewport.
- Automated tests cover partial-name search, each filter in isolation, two
  filters together, query-string persistence, and the empty state. CI passes.

### Definition of done

The engineering PR is reviewed and merged; the deployed page satisfies every
criterion above with the seeded dataset; the product owner records the
acceptance result on issue #7; and the issue is then closed by the team.

### Handoff and dependencies

This is the first Sprint 2 feature. Its college rows and detail links are the
entry points used by #8 and #16. It should not introduce a new dependency or
change project-wide settings without coordinating with the deployment owner.

---

## #8 - Add and remove colleges on my shortlist

### User story

**As a logged-in student, I want to save and remove colleges on a personal
shortlist, so that I can keep the schools I care about in one place rather than
scattered across tabs and spreadsheets.**

### Narrative and pain point

Finding a promising school does not mean a student is ready to apply. Without
a private place to collect candidates, they lose useful discoveries, duplicate
research, or accidentally mix their choices with someone else's. The list must
also stay accurate when a school stops fitting their plan.

### How the product solves it

Give each signed-in student a personal shortlist. From a college result or
detail page, the student uses a CSRF-protected POST form to add or remove that
college. The interface always reflects the saved state after a reload; removal
asks for confirmation so an accidental click does not discard a choice.

### Scope and acceptance criteria

- Every college row and detail page provides an add/remove control implemented
  as a CSRF-protected `<form method="post">`, never as a GET link.
- `/shortlist/` shows only the signed-in visitor's saved colleges. A logged-out
  visitor is sent to log in and returns to the intended page through a working
  `?next=` parameter.
- Adding a college twice cannot create a duplicate saved item, and the control
  shows the current saved state after reload.
- Removing a college asks for confirmation and removes only that student's
  saved item.
- A student can save at least 20 colleges, and the shortlist page shows the
  count.
- Automated tests cover add, repeated add, confirmed removal, login redirect,
  and the rule that another user cannot view or remove the student's items. CI
  passes.

### Definition of done

The feature PR is reviewed and merged; a logged-in seeded student can add,
reload, view, and safely remove schools on staging; user isolation and
duplicate protection pass in automated tests; the product owner validates the
criteria on issue #8; and the issue is then closed by the team.

### Handoff and dependencies

#8 depends on #7 providing college rows or a detail page to host the control.
It uses the existing `Shortlist` and `ShortlistItem` data model; any data-model
or account-flow change must be coordinated with the responsible engineers.

---

## #16 - Find schools similar to one I like

### User story

**As a student who has found a school I like, I want to see comparable
colleges and the reasons they are comparable, so that I can discover good fits
I would not have thought to search for by name.**

### Narrative and pain point

Students often know a single aspirational school but cannot translate what they
like about it into a broad search. Name search alone reinforces familiar and
highly marketed schools. They need transparent recommendations based on school
characteristics, not an unexplained ranking or a generative answer.

### How the product solves it

From every college row and detail page, offer a **Find similar** link to
`/colleges/<unitid>/similar/`. The page returns the ten closest institutions
using only College Scorecard fields. It explains each match with two or three
plain-language reasons such as similar size or cost. It never treats a missing
federal value as zero and never uses an LLM.

### Scope and acceptance criteria

- Every college row and detail page links to
  `/colleges/<unitid>/similar/`. The results contain up to 10 institutions and
  never include the source school itself.
- Similarity uses only undergraduate size, cost of attendance, admission rate,
  completion rate, median earnings after 10 years, public/private control, and
  region. Numeric values are normalized; missing values are omitted from the
  comparison rather than interpreted as zero.
- A pgvector feature vector is computed during the seed/import process and
  stored for each comparable institution. It is not recomputed for every web
  request.
- Each listed result displays two or three reasons derived from the closest
  matching features. No LLM participates in the result or explanation.
- A source school with insufficient comparable data shows a short,
  understandable message rather than an error or misleading list.
- The approach is documented in `docs/mgt656/technical.md`. The CI Postgres
  service and both Neon databases enable the `vector` extension, coordinated
  with the deployment owner.
- The seeded-data page renders in under one second on staging.
- Automated tests prove expected neighbour order in a small fixture, correct
  handling of a missing value, exclusion of the source school, and the
  insufficient-data message. CI passes.

### Definition of done

The feature PR is reviewed and merged; vector support is verified in CI and
staging; seeded data produces transparent, valid similar-school results in
under one second; all listed tests pass; the product owner validates the
criteria on issue #16; and the issue is then closed by the team.

### Handoff and dependencies

#16 needs #7's college discovery surface and requires early coordination with
the deployment owner because pgvector affects CI and both hosted databases. It
must not delay #7 or #8 if vector infrastructure is unavailable.
