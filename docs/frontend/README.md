# Frontend Documentation Guide

This directory contains the implementation contracts for the Knowloop frontend.
Read them together with the root frontend source-of-truth files:

1. `DESIGN.md`
2. `SITE.md`
3. `component-rules.md`
4. `frontend-agent.md`

## Directory Purpose

- `page-structures/`: page-specific goals, layout rules, required data, UI guardrails, and route expectations

## Recommended Page Build Order

1. `page-structures/workspace.md`
2. `page-structures/ask.md`
3. `page-structures/wiki.md`
4. `page-structures/review.md`
5. `page-structures/insights.md`
6. `page-structures/learning.md`
7. `page-structures/sources.md`
8. `page-structures/maintenance.md`

## Rules

- do not implement a page without its structure document
- keep route-level behavior aligned with the backend API contracts
- update the page structure doc when the page purpose or layout changes materially
- keep the frontend docs in Korean-user-friendly language where it improves clarity, but do not force unnatural translations
