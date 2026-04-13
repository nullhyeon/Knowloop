# Page Structure: `/wiki`

## Purpose

Browse and inspect the formal wiki as the official knowledge layer.

## Primary Users

- student
- instructor
- operator
- validator

## Core Job

Help the user explore trusted knowledge and understand where that knowledge came from.

## Layout

### Three-Pane Documentation Layout

- left: search, filters, tree/list of pages
- center: wiki document body
- right: metadata and refs

## Required Data

- wiki page list
- wiki page detail

## Required UI Elements

- search input
- page list or tree
- page summary
- document title and body
- metadata panel
- source refs
- candidate refs
- updated timestamp

## States

### Loading

- tree/list skeleton
- body skeleton
- metadata skeleton

### Empty

- explain that no official page exists yet for the current scope

### Error

- show whether the page is missing or inaccessible by scope

## Guardrails

- do not make pages feel like casual notes
- source refs and candidate refs must stay visible
- this page should feel closer to an internal knowledge base than a blog post

## Success Condition

The user understands that the wiki is a maintained, official knowledge layer with traceable inputs.
