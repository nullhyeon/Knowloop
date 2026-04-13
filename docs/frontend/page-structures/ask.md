# Page Structure: `/ask`

## Purpose

Handle the main ask/respond workflow while revealing how the answer was grounded and what the system wrote back.

## Primary Users

- student
- instructor
- operator
- validator

## Core Job

Help the user ask a scoped question and understand:

1. the answer
2. the grounding
3. the resulting system updates

## Layout

### Desktop Three-Pane Layout

- left: recent sessions, quick search, topic history
- center: composer and conversation stream
- right: evidence, runtime, and write-back panel

### Center Column Sections

- page title + current scope
- question composer
- current answer card
- previous turns

### Right Panel Sections

- answer basis
- retrieval refs
- runtime state
- write-back plan results
- created session / candidate / learning effects

## Required Data

- query response payload
- recent sessions
- session search results

## Required UI Elements

- textarea composer
- response mode selector if surfaced
- submit action
- answer card
- evidence chips
- retrieval ref list
- runtime status chip
- write-back result cards
- recent session list

## States

### Loading

- answer placeholder
- right-panel skeleton

### Empty

- default view should still explain what this page does
- show examples that fit Korean academic workflow, not generic AI prompts

### Error

- if query fails, show clear retry state
- if fallback was used, explain it neutrally

## Guardrails

- never make this a centered generic chat homepage
- evidence cannot be hidden by default
- write-back results must be visible after a successful response
- runtime metadata should be informative but not overwhelming

## Success Condition

A user can ask a question and immediately understand both the answer and how the system turned that interaction into durable knowledge state.
