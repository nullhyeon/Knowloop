# Current Todo

## Completed

- [x] Install `uv`
- [x] Install Gemini CLI
- [x] Copy `agent-skills` into `.agents/`
- [x] Create `AGENTS.md` and `GEMINI.md`
- [x] Add FastAPI backend scaffold
- [x] Add bootstrap, test, and lint scripts
- [x] Add initial structured output schemas
- [x] Verify Codex CLI login status
- [x] Configure Gemini CLI auth type
- [x] Complete Gemini CLI Google sign-in on this machine

## Next Up

- [x] Planning lock docs completed and wired into the harness
- [ ] Gemini Pro Critic: perform one final contract review against `data-contracts`, `query-writeback-policy`, `api-contracts`, and `fixture-catalog`
- [x] Codex Builder: implement storage bootstrap for `sessions.db` and `audit.db`
- [x] Codex Reviewer: review the storage bootstrap slice for contract drift and missing tests
- [x] Codex Builder: create the first canonical fixture pack from `docs/product/fixture-catalog.md`
- [ ] Codex Builder: define candidate lifecycle write helpers

## After First Storage Slice

- [x] Gemini Pro Critic: review storage boundaries and identify over-coupled responsibilities
- [ ] Codex Builder: implement raw source registration and manifest updates
- [ ] Codex Builder: implement `POST /api/v1/query/respond` against fixture-driven tests

## Ready-To-Assign Prompt Targets

- Builder prompt: `.agents/prompts/codex-builder.md`
- Reviewer prompt: `.agents/prompts/codex-reviewer.md`
- Critic prompt: `.agents/prompts/gemini-critic.md`
- Backend kickoff prompt: `.agents/prompts/kickoff-backend-foundation.md`
- Storage kickoff prompt: `.agents/prompts/kickoff-storage-bootstrap.md`
