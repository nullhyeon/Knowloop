# Knowloop Frontend Component Rules

## Purpose

This file defines the UI primitives, wrappers, state representations, and implementation boundaries for the Knowloop frontend.

Use it with:

- `DESIGN.md`
- `SITE.md`
- `docs/frontend/page-structures/*`

---

## 1. Implementation Principles

1. Use stable primitives and compose product-specific wrappers.
2. Keep page files focused on layout and orchestration, not low-level UI logic.
3. Do not scatter badge, status, and metadata formatting rules across pages.
4. Do not hardcode colors or spacing in page components when a shared token or wrapper should own the behavior.
5. Keep Korean UI copy readable and concise.

---

## 2. Base Stack Rules

### Recommended UI Foundation

- `shadcn/ui` for primitives
- Tailwind with CSS variables for tokenized theme wiring
- `class-variance-authority` for repeatable variants

### Why

- strong accessibility defaults
- good support for console-grade tables, dialogs, tabs, sheets, and sidebars
- easy ownership of component code in the repo

### Required Constraint

Never ship raw copied blocks without adapting them to Knowloop's object language and layout rules.

---

## 3. Primitive vs Wrapper Model

### Primitives

These are generic UI building blocks and should stay reusable:

- `Button`
- `Input`
- `Textarea`
- `Badge`
- `Tabs`
- `Table`
- `Card`
- `Dialog`
- `Sheet`
- `Tooltip`
- `DropdownMenu`
- `Command`
- `ScrollArea`
- `Separator`
- `Skeleton`

### Product Wrappers

These encode Knowloop semantics and should be used instead of per-page improvisation:

- `ScopeHeader`
- `RoleBadge`
- `ObjectTypeBadge`
- `KnowledgeStateBadge`
- `ConfidenceBadge`
- `RuntimeStatusChip`
- `EvidencePanel`
- `WritebackPanel`
- `WikiMetaPanel`
- `CandidateSummaryRow`
- `CandidatePatchPreview`
- `SourceSummaryRow`
- `MaintenanceCheckRow`
- `InsightPatternCard`
- `LearningGapCard`
- `SessionResultRow`

Rule:

- if a page repeats a semantic pattern twice, promote it to a wrapper

---

## 4. Global Token Rules

### Do

- use CSS variables for colors and surfaces
- map component variants to semantic roles
- keep typography tokenized
- use one shared border radius scale

### Do Not

- hardcode ad hoc hex colors in page files
- invent page-local shadows
- switch typography systems per page
- create one-off spacing systems

---

## 5. Badge Rules

Badges are central to the product.

### Badge Families

#### Object Type

- `Source`
- `Session`
- `Candidate`
- `Wiki Page`
- `Learning Note`

#### Lifecycle / State

- `Open`
- `Promoted`
- `Merged`
- `Dropped`
- `Pending`
- `Synced`
- `Stale`
- `Needs Review`

#### Runtime

- `LLM Rewrite`
- `Fallback`
- `Wiki Grounded`
- `Source Fallback`

#### Scope

- `Academic`
- `Operations`
- `Review`
- course/class tags

### Rules

- keep badge wording stable across pages
- do not rename the same state per screen
- object type and lifecycle may appear together
- avoid more than 3 high-signal badges in the same compact row unless the page is explicitly a dense operations surface

---

## 6. Panel Rules

### Left Sidebar

Must handle:

- nav groups
- active route state
- role/profile identity
- course/class context

Must not contain:

- oversized marketing copy
- decorative illustrations
- page-specific controls that belong in content

### Right Context Panel

Must show one of:

- evidence
- metadata
- patch preview
- audit/activity
- selected object detail

If a page cannot justify the right panel with meaningful content, collapse it deliberately rather than leaving it empty.

---

## 7. Table Rules

### Use Tables For

- sources
- maintenance checks
- session search results
- review queues when density matters

### Table Requirements

- sticky or stable headers when useful
- strong first column hierarchy
- visible empty states
- row click behavior must be obvious
- actions should appear as explicit buttons or row menus, not ambiguous text links

### Do Not

- over-cardify tabular data
- hide key status information inside hover-only interactions

---

## 8. Ask Surface Rules

The ask surface is not a landing-page chat interface.

### Required Subsections

- question composer
- answer display
- answer basis / evidence section
- runtime / grounding metadata
- write-back effects section
- recent sessions or topical history

### Required Wrapper Components

- `EvidencePanel`
- `WritebackPanel`
- `RuntimeStatusChip`
- `SessionResultRow`

### Guardrails

- the answer area must not dominate the entire screen by itself
- evidence must not be buried under a hidden accordion by default
- candidate creation and learning updates should be visible without extra searching

---

## 9. Review Surface Rules

### Required Sections

- candidate list
- candidate detail
- patch preview
- source refs
- audit trail summary
- decision actions

### Required Wrapper Components

- `CandidateSummaryRow`
- `CandidatePatchPreview`
- `ConfidenceBadge`
- `KnowledgeStateBadge`

### Guardrails

- approve / merge / drop must feel deliberate
- patch preview must be readable as knowledge diff, not just code diff
- source traceability must stay visible near review actions

---

## 10. Wiki Surface Rules

### Required Sections

- wiki navigation or search list
- document body
- metadata panel
- refs
- related pages or linked artifacts

### Required Wrapper Components

- `WikiMetaPanel`
- `ObjectTypeBadge`
- `KnowledgeStateBadge`

### Guardrails

- wiki pages must feel official and maintained
- do not style them like freeform personal notes
- source and candidate refs must remain discoverable

---

## 11. Dashboard Rules

### Use For

- `Insights`
- parts of `Learning`
- parts of `Maintenance`

### Structure

- KPI row first
- patterns and grouped findings second
- action queue or next-step list third

### Guardrails

- charts are supporting tools, not the page's identity
- every major metric should imply a next action
- do not create decorative analytics without workflow consequence

---

## 12. Loading, Empty, and Error States

Every page must define all three.

### Loading

- use skeletons that resemble the eventual layout
- keep right-panel loading states aligned with actual panel structure

### Empty

- explain why the state is empty
- suggest the next meaningful action
- avoid generic `No data` messaging

### Error

- use calm operational language
- show retry affordance where appropriate
- expose enough context for debugging without leaking backend internals

---

## 13. Data Boundary Rules

### Page Components

- may fetch and orchestrate
- should not own deep formatting logic

### Hooks

- own data fetching, transformation, and stateful orchestration
- examples: `useContextProfile`, `useQueryRespond`, `useReviewCandidate`, `useWikiPage`

### Data Mappers

- normalize API payloads into UI-friendly structures
- keep backend envelope knowledge out of leaf components

### Mock / Fixture Data

- store UI development fixtures in dedicated mock data files
- align naming with backend object language

---

## 14. File Organization Rules

Recommended structure:

```text
src/
  app/
  components/
    ui/
    shell/
    ask/
    learning/
    wiki/
    review/
    insights/
    sources/
    maintenance/
  hooks/
  lib/
  data/
```

Rules:

- `components/ui/` only for primitives
- page semantics belong in feature folders
- shared shell components stay under `components/shell/`
- avoid giant page files with embedded subcomponents

---

## 15. Copy and Label Rules

- default labels should be Korean
- keep common technical English where expected
- use short action verbs for buttons
- keep helper text direct and factual
- avoid overexplaining in cards and badges

Examples:

- `Search`
- `Wiki Page`
- `View Evidence`
- `Pending Review`
- `Fix Error`

---

## 16. Validation Rules

Before a frontend slice is done:

1. the page matches `DESIGN.md`
2. the page matches its page structure doc
3. shared wrappers are reused where expected
4. object states are visually consistent
5. Korean copy reads naturally
6. empty/loading/error states exist
7. the page still feels like part of one product shell
