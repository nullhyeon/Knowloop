# Knowloop Frontend Agent Guide

## Purpose

This file is the operating guide for Codex when implementing Knowloop frontend work.

Read it before changing any frontend code or generating any frontend page.

---

## 1. Frontend Mission

Build Knowloop as a Korean-friendly knowledge operations console, not as a generic AI chat app.

The frontend must make these truths obvious:

1. the system stores and structures knowledge over time
2. the wiki is the official knowledge layer
3. candidate review is a first-class workflow
4. student, instructor, operator, and validator see different but connected views of the same system

---

## 2. Canonical Reading Order

For frontend work, read in this order:

1. `DESIGN.md`
2. `SITE.md`
3. `component-rules.md`
4. `docs/frontend/README.md`
5. the relevant file from `docs/frontend/page-structures/`
6. `docs/architecture/api-contracts.md`
7. `docs/product/role-permissions.md`
8. `AGENTS.md`
9. `SPEC.md`

If these disagree, follow:

1. `AGENTS.md`
2. `SITE.md`
3. `DESIGN.md`
4. page structure docs

Then update the stale document instead of improvising silently.

---

## 3. Frontend Working Rules

### One Slice at a Time

Never try to implement the entire frontend in one pass.

Work in this order:

1. public product entry page
2. workspace entry and shell
3. ask surface
4. wiki surface
5. review surface
6. insights surface
7. learning
8. sources
9. maintenance

### One Responsibility per Slice

Examples of valid slices:

- public entry hero and sample-start section
- workspace shell and context switch
- ask page main layout
- ask evidence panel
- wiki list/detail composition
- review patch preview panel

Examples of invalid slices:

- build the entire product UI
- finish all dashboard pages
- redesign every route at once

---

## 4. Frontend Build Loop

For each slice:

1. confirm the backend contract already exists
2. read the matching page structure doc
3. implement the smallest meaningful UI slice
4. verify shared wrappers and badges
5. run frontend verification
6. perform Critic and Reviewer checks using a narrow review package
7. then commit

Do not skip the page structure step.

---

## 5. Frontend Critic Focus

When acting as Critic, challenge:

- whether the page still looks like a knowledge console
- whether the page reveals the right object states
- whether the page hides key evidence or metadata
- whether Korean copy sounds unnatural or overly translated
- whether page-local styling drifts from the global shell
- whether a page is becoming a generic dashboard or generic chat UI

Critic is not mainly for naming minor CSS issues.

---

## 6. Frontend Reviewer Focus

When acting as Reviewer, check:

- correctness of component boundaries
- prop shape drift
- missing loading / empty / error states
- broken responsive behavior
- badge and state inconsistency
- missing accessibility or focus handling
- duplicated wrapper logic that should be shared

---

## 7. Required Design Rules

- use `DESIGN.md` as the global visual source of truth
- use `SITE.md` for routes, nav, and page relationships
- use `component-rules.md` for primitive/wrapper boundaries
- use page structure docs for layout
- keep Korean users first in copy and reading rhythm
- allow English only where it feels natural in Korean tech workflow tools

---

## 8. Korean-Friendly UI Rules

- default to Korean UI labels
- do not translate every technical term mechanically
- prefer short, direct labels
- use enough spacing and line-height for Korean readability
- avoid English-heavy dense admin jargon unless the term is standard

Good:

- `Search`
- `View Evidence`
- `Pending Review`
- `Recent Sessions`

Bad:

- `Launch onboarding flow for immediate start`
- `High-level interactive view for data insights`

---

## 9. Ask Page Special Rule

The ask page is the highest-risk page for design drift.

Never build it as:

- a centered hero chat box
- a blank conversation canvas
- an AI landing page clone

It must always show:

- answer
- answer basis
- evidence
- runtime status
- write-back effects
- recent history or context

---

## 10. Public Entry Page Rule

The `/` page is not a generic marketing site.
It is a demo entry surface for judges and first-time users.

It must always show:

- what Knowloop is
- how it works in one short workflow section
- why it is not just a chatbot
- two obvious seeded entry buttons
  - `학생용 샘플 데이터로 시작`
  - `교강사용 샘플 데이터로 시작`

It must not:

- bury the entry buttons below long feature marketing
- rely on vague AI slogans
- look unrelated to the in-product console

---

## 11. Shared Object Language

Always use the same object names:

- Source
- Session
- Candidate
- Wiki Page
- Learning Note

Always use the same lifecycle language:

- Open
- Promoted
- Merged
- Dropped
- Pending
- Synced
- Stale
- Needs Review

Never rename these per page.

---

## 12. Component Ownership Rules

- primitives live in `components/ui`
- semantic wrappers live in feature or shared folders
- pages compose, not reinvent
- API envelope parsing belongs in hooks or data mappers, not leaf components
- no inline one-off status badges when a shared badge component already exists

---

## 13. Do Not Do These

- do not use chat-product references as the main shell
- do not create visually different mini-products per page
- do not overuse gradients, glows, or glassmorphism
- do not turn the public entry page into a glossy startup landing page
- do not let insights become a meaningless chart gallery
- do not hide traceability behind hover-only UI
- do not design for mobile first at the expense of desktop console quality

---

## 14. Required Deliverables Per Page

Before a page is considered complete, it must have:

1. a stable route
2. a page structure match
3. clear loading state
4. clear empty state
5. clear error state
6. scope visibility
7. object-state visibility
8. right-panel behavior defined

---

## 15. Frontend Handoff Format

When handing a frontend slice to Critic or Reviewer, include:

1. route
2. slice goal
3. files changed
4. relevant page structure doc
5. shared wrappers involved
6. verification performed
7. specific questions or risks
