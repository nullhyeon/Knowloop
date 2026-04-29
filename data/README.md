# Data Layout

The `data/` directory mirrors the architecture described in the product docs.

Committed here:

- directory structure
- safe metadata files
- placeholder `.gitkeep` files
- repository-safe fixture directories under `fixtures/`

Do not commit:

- real educational raw sources
- real student sessions
- private operational notes
- generated SQLite databases with private data

## Layers

- `raw/` original source material
- `sessions/` searchable interaction history
- `candidate/` unverified or transitional knowledge
- `wiki/` promoted knowledge artifacts
- `learning/` student-specific learning outputs
- `meta/` manifests, scoped maintenance status, and local database files
- `fixtures/` synthetic inputs and expected snapshots for tests
