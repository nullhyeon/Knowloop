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
- [x] Codex Builder: implement storage bootstrap for `sessions.db` and `audit.db`
- [x] Codex Reviewer: review the storage bootstrap slice for contract drift and missing tests
- [x] Codex Builder: create the first canonical fixture pack from `docs/product/fixture-catalog.md`
- [x] Codex Builder: define candidate lifecycle write helpers
- [x] Codex Critic fallback: review the candidate lifecycle slice when Gemini Pro is blocked
- [x] Codex Reviewer: review the candidate lifecycle slice for contract drift and missing tests
- [x] Codex Builder: implement dedicated review workflow endpoints
- [x] Gemini Pro Critic: review the review workflow slice for route boundaries, replay safety, and scaling gaps
- [x] Codex Critic fallback: follow up on the review workflow slice and harden the flagged gaps
- [x] Codex Reviewer: review the review workflow slice for correctness, replay coverage, and contract drift

## After First Storage Slice

- [x] Gemini Pro Critic: review storage boundaries and identify over-coupled responsibilities
- [x] Codex Builder: implement raw source registration and manifest updates
- [x] Codex Critic fallback: review the raw source slice for boundary, validation, and contract drift
- [x] Codex Reviewer: review the raw source slice for correctness and missing tests
- [x] Codex Builder: implement `POST /api/v1/query/respond` against fixture-driven tests
- [x] Codex Critic fallback: review the `query/respond` slice for write-back integrity, role boundaries, and hidden coupling
- [x] Codex Reviewer: review the `query/respond` slice for correctness, contract drift, and missing tests

## Next Slice

- [x] Codex Builder: implement dedicated wiki listing and detail endpoints
- [x] Gemini Pro Critic: review the wiki read slice for role exposure, contract clarity, and coupling
- [x] Codex Critic fallback: not needed because Gemini Pro completed the wiki read critic pass
- [x] Codex Reviewer: review the wiki read slice for correctness, contract drift, and missing tests
- [x] Codex Builder: implement instructor insight endpoints against fixture-driven tests
- [x] Gemini Pro Critic: attempted to review the instructor insight slice but did not complete in time
- [x] Codex Critic fallback: review the insight slice when Gemini Pro could not complete the critic pass
- [x] Codex Reviewer: review the insight slice for correctness, contract drift, and missing tests

## Up Next

- [x] Codex Builder: implement session search endpoints and contract tests
- [x] Gemini Pro Critic: attempted to review the session search slice but did not complete in time
- [x] Codex Critic fallback: review the session-search slice when Gemini Pro could not complete the critic pass
- [x] Codex Reviewer: review the session search slice for correctness, contract drift, and missing tests

## Coming Next

- [x] Codex Builder: implement maintenance and stale-detection outputs
- [x] Gemini Pro Critic: attempted to review the maintenance slice but did not complete in time
- [x] Codex Critic fallback: review the maintenance slice when Gemini Pro could not complete the critic pass
- [x] Codex Reviewer: review the maintenance slice for correctness, contract drift, and missing tests

## Next After Maintenance

- [ ] Codex Builder: document backend runbook and handoff expectations
- [ ] Gemini Pro Critic: review the runbook slice for operational clarity and handoff gaps
- [ ] Codex Critic fallback: run when Gemini Pro cannot complete the runbook critic pass
- [ ] Codex Reviewer: review the runbook slice for contract drift and missing operator guidance

## Ready-To-Assign Prompt Targets

- Builder prompt: `.agents/prompts/codex-builder.md`
- Critic fallback prompt: `.agents/prompts/codex-critic.md`
- Reviewer prompt: `.agents/prompts/codex-reviewer.md`
- Critic prompt: `.agents/prompts/gemini-critic.md`
- Backend kickoff prompt: `.agents/prompts/kickoff-backend-foundation.md`
- Storage kickoff prompt: `.agents/prompts/kickoff-storage-bootstrap.md`
