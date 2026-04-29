# Page Structure: `/workspace`

## Purpose

Provide the role-aware entry into Knowloop.
This page establishes the current working context and makes the product feel like a workspace tool rather than a blank app.

## Primary Users

- student
- instructor
- operator
- validator

## Core Job

Help the user answer one question immediately:

`What role and course/class context should I enter right now?`

## Layout

### Main Structure

- top: page title and short explanation
- center: role and scope selection cards
- lower section: recent contexts and recommended entry points

### Recommended Composition

- left area: current workspace concept and short guidance
- right area: recent contexts or `continue where you left off`

## Required Data

- canonical resolved context

## Required UI Elements

- role/scope cards
- role badge
- course/class labels
- domain label
- `Enter workspace` action
- `Recent contexts` list

## States

### Loading

- loading skeleton for profile cards and recent contexts

### Empty

- if no recent contexts exist, guide the user to choose a role and scope manually

### Error

- if context cannot resolve, show retry and explain the entry setup failed

## Guardrails

- do not turn this into a marketing welcome screen
- do not hide the current role and class scope
- do not force the user to type headers or technical context values

## Success Condition

The user can enter the correct role, course, and class context without ambiguity in one interaction.
