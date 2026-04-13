# Page Structure: `/insights`

## Purpose

Provide instructors with aggregate, actionable insight into repeated confusion and review priority.

## Primary Users

- instructor

## Core Job

Help the instructor answer:

`지금 어떤 주제를 다시 가르쳐야 하고, 어떤 후보를 먼저 검토해야 하는가?`

## Layout

### Dashboard + Priority Lists

- top: KPI summary row
- middle: top topics, gap clusters, candidate totals
- side or lower section: priority actions and drill-down links

## Required Data

- overview insight payload
- pattern list payload

## Required UI Elements

- KPI cards
- top topic list
- gap cluster list
- pattern cards
- priority review links
- quick links into wiki or review

## States

### Loading

- KPI skeletons
- list placeholders

### Empty

- explain that enough student activity has not accumulated yet

### Error

- surface the failure without turning the page into a system-debug surface

## Guardrails

- charts are optional, not mandatory
- actionability matters more than analytics flashiness
- do not expose raw student transcript text

## Success Condition

An instructor can immediately identify what to teach next and what to review next.
