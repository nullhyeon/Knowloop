# Page Structure: `/learning`

## Purpose

Expose the student's learning continuity: recent confusion, learning notes, and next actions.

## Primary Users

- student

## Core Job

Answer:

`What do I still not understand, and what should I revisit now?`

## Layout

### Dashboard + Action Queue

- top: learning summary
- middle-left: recent learning notes
- middle-right: gap tracker
- bottom: next actions and related wiki links

## Required Data

- session-derived learning outputs
- recent learning note summaries
- next action items

## Required UI Elements

- summary cards
- gap cards
- next action checklist
- related wiki links
- recent question history snippets

## States

### Loading

- KPI skeletons
- list placeholders

### Empty

- explain that learning notes appear after asking grounded questions

### Error

- keep messaging calm and action-oriented

## Guardrails

- do not make this a task app
- do not make this a generic note app
- learning outputs must remain tied to real sessions and wiki context

## Success Condition

The page feels like a personal study console, not just a history viewer.
