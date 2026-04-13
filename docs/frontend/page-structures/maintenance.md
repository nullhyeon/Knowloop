# Page Structure: `/maintenance`

## Purpose

Expose maintenance health, stale items, and repair-needed findings for the current scope.

## Primary Users

- validator
- system-facing operational users
- instructor as a read-only health consumer where allowed

## Core Job

Show whether the knowledge system is healthy and what needs operational attention.

## Layout

### Status + Findings Layout

- top: maintenance summary and health score
- middle: findings grouped by severity
- right: selected finding detail or report metadata

## Required Data

- maintenance status
- maintenance report

## Required UI Elements

- status banner
- health score display
- severity filters
- findings list
- selected finding details
- report time / scope metadata

## States

### Loading

- summary skeleton
- findings skeleton

### Empty

- if no report exists yet, explain that the report has not run

### Error

- distinguish between `not run` and `report unreadable`

## Guardrails

- this page should feel trustworthy and operational
- avoid decorative charting
- severe findings must be easy to distinguish at a glance

## Success Condition

The user can quickly tell whether the system is healthy and which issues need repair first.
