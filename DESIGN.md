# Knowloop Frontend Design System

## Purpose

`DESIGN.md` is the visual source of truth for the Knowloop frontend.
It exists so Codex, Stitch-style agents, and human developers can keep the same design language across every screen.

Knowloop is not a chat product with a knowledge tab.
It is a role-aware knowledge operations console for Korean education teams.
The interface must always communicate these truths:

1. questions become durable knowledge artifacts
2. official answers come from maintained wiki context, not raw chat alone
3. candidate review and promotion are first-class workflows
4. students, instructors, operators, and validators see the same system through different permissions

This file defines the global visual language only.
Each page must still follow its own page-structure document under `docs/frontend/page-structures/`.

---

## 1. Visual Theme & Atmosphere

Knowloop should feel like a calm, precise, high-trust B2B tool used by real education teams every day.
The product should feel operational and structured, not playful, glossy, or futuristic.

The desired atmosphere is:

- calm and confident rather than loud
- dense enough for serious work, but never cramped
- editorial and information-rich rather than decorative
- knowledge-first, not chatbot-first
- Korean-friendly in rhythm and readability

Reference blend:

- `Linear` for the global shell, spacing rhythm, and dense list/detail composition
- `NotebookLM` for the ask page's evidence-oriented side panel
- `GitBook` for wiki browsing and maintained knowledge pages
- `GitHub` review flows for candidate inspection and approval
- `Stripe` and `Vercel` for dashboards, operational metrics, and clarity of status
- `Sentry` for maintenance and repair-oriented surfaces

The UI must never feel like:

- a centered AI chat landing page
- a glossy marketing site
- a playful edtech app for children
- a BI dashboard full of charts but weak on actionability

### Product Entry Exception

The public product entry page at `/` is the only surface allowed to feel slightly more editorial than the inner console.
Even there, the product must still feel like a real tool, not a generic AI landing page.

Reference priority for `/`:

- `Linear` for the hero layout, product confidence, and CTA discipline
- `GitBook` for the "how it works" sequence and maintained knowledge messaging
- `NotebookLM` Korean product copy tone for evidence-based AI explanation
- `Slite` for trust, knowledge quality, and maintenance messaging
- `Vercel` only for subtle operational trust signals

Rules for `/`:

- show the product as a knowledge operations system, not a chatbot homepage
- keep the hero concise and product-first
- show the workflow `question -> accumulate -> review -> promote -> explore`
- make sample-entry buttons obvious and high-trust
- use Korean-first copy with only natural English nouns such as `Ask`, `Wiki`, `Review`

---

## 2. Design Principles

1. Keep the app looking like one system, not a set of unrelated pages.
2. Make the object model visible: `Source`, `Session`, `Candidate`, `Wiki Page`, `Learning Note`.
3. Show state transitions clearly: `Raw`, `Open`, `Pending`, `Promoted`, `Merged`, `Dropped`, `Synced`, `Stale`, `Needs Review`.
4. Keep evidence, write-back, and review metadata visible where decisions happen.
5. Prefer semantic design language over utility-class language.
6. Use Korean-first copy and readable pacing, while allowing natural English for standard product terms.

---

## 3. Color Palette & Roles

Use semantic roles, not page-local palettes.
The same meaning should always use the same tone.

### Core Surfaces

- `Porcelain Slate` `#F6F7F9` for the main canvas
- `Soft Paper White` `#FCFCFD` for cards and stable content surfaces
- `Clouded Divider Gray` `#E6E8EC` for separators, borders, and subtle lines

### Text Hierarchy

- `Graphite Ink` `#111827` for headings and key figures
- `Steel Body` `#374151` for main body copy and labels
- `Muted Interface Gray` `#6B7280` for metadata, helper text, and timestamps

### Actions and Signals

- `Deep Signal Blue` `#2563EB` for primary actions, selected nav, and active filters
- `Teal Evidence` `#0F766E` for grounding, evidence, and trusted references
- `Plum Review` `#7C3AED` for review workflow emphasis only
- `Verified Green` `#15803D` for synced, approved, or healthy states
- `Pending Amber` `#D97706` for pending, in-progress, or needs-attention states
- `Risk Red` `#DC2626` for blocking errors and rejected states
- `Neutral Slate Blue` `#64748B` for informational runtime messages

### Color Rules

- Keep most of the UI neutral.
- Use accent colors sparingly and consistently by meaning.
- Never use purple as a general brand color; reserve it for review flows.
- Never use bright green or bright red as large area fills.
- Prefer badges, chips, and thin indicators over saturated status cards.

---

## 4. Typography Rules

### Font Families

- Primary UI font: `Pretendard Variable`, fallback `Noto Sans KR`, then system sans-serif
- Monospace font: `IBM Plex Mono`, fallback `JetBrains Mono`, then system monospace

### Korean-Friendly Rules

- Prefer Korean labels and body copy by default.
- Keep English where it is more natural or standard: `Ask`, `Wiki`, `Review`, `Source`, `Sync`, `API`, `Runtime`.
- Avoid forced literal translation for technical terms.
- Avoid all-caps labels as a primary pattern.
- Use generous line-height for Korean text.

### Type Scale

- H1: 30-34px, 700
- H2: 22-26px, 700
- H3: 16-18px, 600
- Body large: 15-16px, 400-500
- Body standard: 14px, 400-500
- Meta / labels: 12-13px, 500
- KPI numerals: 24-32px, 700

### Reading Rhythm

- Body line-height should generally stay between 1.6 and 1.75.
- Dense tables may go slightly tighter, but never below 1.45.
- Korean help text should wrap naturally.

---

## 5. Component Stylings

### Buttons

- Use gently rounded corners, around 10px radius.
- Primary buttons use `Deep Signal Blue`.
- Destructive actions use `Risk Red` only when the action is truly irreversible.
- Secondary actions should be outlined or soft-fill, never decorative.
- Button labels should stay short and explicit.

### Badges and Chips

Knowloop depends heavily on object and state badges.
They must stay stable across pages.

Examples:

- `Source`
- `Session`
- `Candidate`
- `Wiki Page`
- `Learning Note`
- `Open`
- `Pending`
- `Promoted`
- `Merged`
- `Dropped`
- `Synced`
- `Stale`
- `Needs Review`
- `LLM Rewrite`
- `Fallback`
- `Wiki Grounded`
- `Source Fallback`

### Cards and Panels

- Cards should feel operational, not promotional.
- Use subtle borders first and shadows second.
- The right-side evidence panel should have slightly stronger separation than ordinary cards.

### Tables

- Tables are core to `Sources`, `Review`, `Insights`, `Maintenance`, and some `Wiki` surfaces.
- Use compact rows with strong alignment.
- Important columns should stay easy to scan at a glance.
- Avoid burying critical status under hover-only affordances.

### Inputs

- Search bars should be wide and calm.
- The ask composer should feel like a working console input, not a chat landing hero.
- Use clear helper text for attachments, scope, and response mode.

### Diff and Patch Preview

- Review diff panels should borrow from GitHub's clarity, not its exact styling.
- Additions and removals must remain readable in Korean-heavy text.
- Patch preview is a knowledge diff, not a code editor.

---

## 6. Layout Principles

### Global Shell

All primary authenticated pages should use the same shell:

- left sidebar for role-aware navigation and current scope
- main content area for the page-specific work surface
- right context panel for evidence, metadata, patch preview, or selected object detail

The right panel is a product pattern, not an optional flourish.

### Density and Width

- Design for large desktop widths first.
- The main shell should feel comfortable around 1280px to 1440px wide.
- Dense lists are welcome, but panels must keep breathing room.

### Responsive Behavior

- Desktop is the primary canvas for MVP.
- Tablet should remain usable.
- Mobile should not be the primary optimization target yet, but pages must not break.

### Information Hierarchy

The user should always know:

- where they are
- what object they are looking at
- what state that object is in
- what action is available next

---

## 7. Product Objects and States

These objects must appear consistently across the app:

- `Source`
- `Session`
- `Candidate`
- `Wiki Page`
- `Learning Note`

These states must stay stable across pages:

- `Raw`
- `Draft`
- `Open`
- `Pending`
- `Promoted`
- `Merged`
- `Dropped`
- `Synced`
- `Stale`
- `Needs Review`

Rules:

- do not invent per-page names for the same object
- do not rename the same state differently on different screens
- candidate-related pages must always expose kind, confidence, target page, source refs, and lifecycle state

---

## 8. Korean Language and Copy Rules

### Default Language

- Body copy, labels, and helper text should default to Korean.
- Keep the tone clear, calm, and operational.
- Avoid awkward literal translations.

### Allowed English

English is fine when it is already standard in Korean tech products:

- Ask
- Wiki
- Review
- Source
- Sync
- Runtime
- API
- Profile

### Copy Style

- Prefer short labels in navigation.
- Prefer action-oriented buttons.
- Keep system messages factual and reassuring.
- Avoid hype language and avoid childish edtech tone.

Good example:

- `Review the concepts students in this class struggle with most.`

Bad example:

- `Fun learning cards are waiting for you today!`

---

## 9. Motion and Accessibility

- Motion should be subtle and purposeful.
- Good animation targets are panel transitions, list selection emphasis, and diff preview reveal.
- Avoid floating, bouncing, or overly soft motion.
- Focus states must be visible.
- Color should never be the only state indicator.
- Contrast must stay strong enough for dense Korean text.

---

## 10. Implementation Notes for Codex

When implementing UI from this design system:

- describe design in semantic language, not utility-class language
- keep the global shell stable across pages
- use page-specific structure docs for layout details
- never treat `/ask` as a standalone chat landing page
- prioritize Korean readability over flashy density tricks
- use a consistent badge system for product objects and states

If a design decision conflicts with page function, page function wins.
If a page-specific structure conflicts with this file, update `DESIGN.md` rather than improvising silently.
