# Page Structure: `/review`

## Purpose

Process candidate knowledge through approval, merge, drop, and recovery workflows.

## Primary Users

- instructor
- operator (read-only where applicable)
- validator

## Core Job

Help reviewers decide whether a candidate should become official knowledge, merge into another candidate, or be dropped.

## Layout

### Review Console Layout

- left: candidate queue
- center: candidate detail and evidence
- right: patch preview and action panel

## Required Data

- candidate list
- candidate detail
- audit events
- patch preview
- available actions

## Required UI Elements

- candidate queue filters
- candidate detail header
- status and confidence badges
- source refs
- audit summary
- patch preview diff
- approve / merge / drop / resume actions

## States

### Loading

- queue skeleton
- detail skeleton
- preview skeleton

### Empty

- explain that there are no candidates in the current scope or filter

### Error

- show whether the candidate is missing, forbidden, or conflicted

## Guardrails

- this page must feel like a knowledge review workflow, not a generic inbox
- action buttons must remain deliberate and well separated
- patch preview must be visible before final approval

## Success Condition

A reviewer can understand a candidate's provenance and lifecycle, inspect the patch preview, and act confidently.
