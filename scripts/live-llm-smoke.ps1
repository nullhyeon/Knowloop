$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "lib\\resolve-uv.ps1")

$repoRoot = Split-Path -Parent $PSScriptRoot
$apiRoot = Join-Path $repoRoot "apps\\api"
$uv = Get-UvCommand

$pythonScript = @'
from knowloop_api.core.config import Settings
from knowloop_api.core.contracts import ActorRole, RequestDomain
from knowloop_api.services.llm_runtime import (
    EvidenceBlock,
    LLMAnswerContext,
    build_llm_runtime_status,
    generate_grounded_answer,
)

settings = Settings()
status = build_llm_runtime_status(settings)
if not status["enabled"] or not status["configured"]:
    raise SystemExit("Live LLM smoke requires KNOWLOOP_LLM_ENABLED=true and a configured KNOWLOOP_OPENAI_API_KEY.")

context = LLMAnswerContext(
    role=ActorRole.STUDENT,
    domain=RequestDomain.ACADEMIC,
    response_mode="teaching",
    question="When should I use the chain rule?",
    answer_basis=("formal_wiki",),
    fallback_answer="Use the chain rule when one function is nested inside another.",
    evidence_blocks=(
        EvidenceBlock(
            label="formal_wiki",
            lines=(
                "Title: Chain rule",
                "Summary: Use the chain rule for nested functions.",
            ),
        ),
    ),
    request_id="req-live-llm-smoke",
)

answer = generate_grounded_answer(settings, context=context)
if not answer:
    raise SystemExit("Live LLM smoke did not produce a grounded rewrite.")

print("Live LLM smoke passed.")
print(answer)
'@

Push-Location $apiRoot
try {
    $pythonScript | & $uv run python -
}
finally {
    Pop-Location
}
