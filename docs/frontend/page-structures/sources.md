# Page Structure: `/sources`

## Purpose

Browse and register raw sources that feed the knowledge system.

## Primary Users

- instructor
- operator
- validator

## Core Job

Show what raw materials exist and how they connect to downstream knowledge objects.

## Layout

### Table + Detail Panel

- left / center: source table
- right: selected source detail panel

## Required Data

- source list
- source detail

## Required UI Elements

- source table
- filters by source type, domain, status
- register source action
- source detail panel
- scope badges
- linked object summary where available

## States

### Loading

- table skeleton
- detail panel skeleton

### Empty

- guide the user to register the first source for this scope

### Error

- explain registration failure or retrieval failure clearly

## Guardrails

- do not make this page feel like a generic cloud storage browser
- traceability matters more than visual decoration
- metadata must remain easy to scan

## Success Condition

The user can understand which source artifacts exist and how they relate to the knowledge pipeline.
