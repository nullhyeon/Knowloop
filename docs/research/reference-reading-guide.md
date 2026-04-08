# LLM Wiki 레퍼런스 리딩 가이드

## 1. 문서 목적

이 문서는 Knowloop 설계를 위해 참고한 LLM Wiki 계열 구현체를 어떤 순서로 읽으면 구조를 빠르게 이해할 수 있는지 정리한 연구 가이드다.

목표는 모든 저장소를 다 읽는 것이 아니라 다음 3가지를 빠르게 확보하는 것이다.

1. `철학과 문제의식`
2. `프로토콜과 데이터 구조`
3. `실제 구현 방식`

주의:
- 이 문서에서 등장하는 `AGENTS.md`, `CLAUDE.md`, `config.yaml` 같은 파일명은 각 외부 레퍼런스 저장소 내부 파일을 뜻한다.
- Knowloop의 현재 실행 규칙은 이 문서가 아니라 루트 `AGENTS.md`, `GEMINI.md`, `docs/README.md`를 기준으로 판단한다.

---

## 2. 가장 추천하는 읽기 전략

읽는 순서는 다음 4단계가 가장 좋다.

1. `Karpathy 원문 + 비판 댓글`
2. `프로토콜/스키마형 레포`
3. `실제 구현형 레포`
4. `교육용으로 바로 쓰기 좋은 학습 레이어 레포`

이 순서가 좋은 이유는,
- 처음부터 구현만 보면 왜 그런 구조가 필요한지 놓치기 쉽고
- 반대로 철학만 보면 실제로 어떻게 짜야 하는지 감이 안 오기 때문이다.

---

## 3. 1차 필독 순서

## 3.1 Karpathy 원문

### 읽을 링크
- [Karpathy gist 본문](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)

### 꼭 볼 포인트
- `raw / wiki / schema`
- `ingest / query / lint`
- `index.md / log.md`
- query 결과도 다시 위키에 filing 하는 아이디어

### 메모할 질문
- 우리 서비스에서 raw는 무엇인가?
- 우리 서비스에서 wiki는 누구를 위한 것인가?
- query 결과를 어디에 다시 쌓을 것인가?

---

## 3.2 댓글에서 꼭 볼 논점

### 꼭 체크할 링크
- [Karpathy gist 댓글 전체](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)
- [pnakamura companion gist](https://gist.github.com/pnakamura/026c0152bb9234424bc5954c320201d8)

### 꼭 봐야 할 논점
- query가 커지면 파일 인덱스만으로 버티기 어렵다
- schema는 결국 생긴다
- candidate/provisional layer가 필요하다
- librarian / validator gate가 필요하다
- 자동 요약은 학습 형성을 대체하지 못한다

---

## 4. 2차 필독 순서: 프로토콜과 구조

## 4.1 `Nimo1987/atomic-knowledge`

### 저장소
- [atomic-knowledge](https://github.com/Nimo1987/atomic-knowledge)

### 읽을 파일 순서
1. `README.md`
2. `AGENT.md`
3. `docs/GOLDEN_PATH.md`
4. `docs/CANDIDATE_LIFECYCLE.md`
5. `docs/LINT_WORKFLOW.md`
6. `docs/AGENT_NATIVE_USAGE.md`
7. `example-kb/WALKTHROUGH.md`

### 왜 먼저 읽는가
- formal wiki와 candidate layer를 가장 잘 나눠놓았다.
- 교육용으로 옮길 때 가장 중요한 `미완성 지식 관리`를 배울 수 있다.

### 읽고 나서 얻어야 할 것
- candidate 상태 모델
- active / recent / index / log 구조
- 승격/병합/폐기 기준

---

## 4.2 `dkushnikov/mnemon`

### 저장소
- [mnemon](https://github.com/dkushnikov/mnemon)

### 읽을 파일 순서
1. `README.md`
2. `protocols/storage.md`
3. `extract-schema.md`
4. `templates/core/*`
5. `reader-context` 관련 문서

### 왜 읽는가
- 같은 자료라도 학생 맥락에 따라 다른 추출이 필요하다는 걸 보여준다.
- 교육용 개인화의 핵심 사고방식을 준다.

### 읽고 나서 얻어야 할 것
- `source.md` immutable / `extract.md` mutable 사고방식
- reader-context 기반 개인화 추출 방식

---

## 4.3 `arturseo-geo/llm-knowledge-base`

### 저장소
- [llm-knowledge-base](https://github.com/arturseo-geo/llm-knowledge-base)

### 읽을 파일 순서
1. `README.md`
2. `AGENTS.md`
3. `docs/learning-layer.md`
4. `docs/contamination-mitigation.md`
5. `docs/why-not-rag.md`

### 왜 읽는가
- 위키를 학습 성과로 연결하는 구조가 가장 직접적이다.
- flashcard, gap tracker, review queue가 교육 솔루션에 바로 연결된다.

### 읽고 나서 얻어야 할 것
- learning layer 구조
- contamination mitigation
- 자동 정리와 실제 학습 개입의 연결 방식

---

## 5. 3차 필독 순서: 실제 구현 감각

## 5.1 `xoai/sage-wiki`

### 저장소
- [sage-wiki](https://github.com/xoai/sage-wiki)

### 읽을 파일 순서
1. `README.md`
2. `cmd/sage-wiki/main.go`
3. `internal/compiler/pipeline.go`
4. `internal/query/query.go`
5. `internal/linter/passes.go`
6. `internal/manifest/manifest.go`
7. `internal/prompts/prompts.go`
8. `web/src/`

### 왜 읽는가
- 조사한 구현체 중 가장 완성된 end-to-end 제품형이다.
- compile, query, lint, serve까지 전체 흐름을 이해하기 좋다.

### 읽고 나서 얻어야 할 것
- 파이프라인 분해 방식
- search + synthesis 구성
- web UI가 어느 수준까지 필요한지 감

---

## 5.2 `wastedcode/memex`

### 저장소
- [memex](https://github.com/wastedcode/memex)

### 읽을 파일 순서
1. `README.md`
2. `docs/architecture.md`
3. `docs/prompts.md`
4. `src/daemon.ts`
5. `src/daemon/server.ts`
6. `src/daemon/runner.ts`
7. `src/daemon/scaffold.ts`
8. `src/lib/prompts/wiki.ts`
9. `src/lib/prompts/ingest.ts`
10. `src/lib/prompts/query.ts`
11. `src/lib/prompts/lint.ts`

### 왜 읽는가
- 운영 환경에서 지속적으로 위키를 돌릴 때 필요한 구조를 보여준다.
- queue, audit, daemon, scaffold, prompt 분리가 명확하다.

### 읽고 나서 얻어야 할 것
- wiki별 직렬 처리 개념
- audit log 사고방식
- schema/index/log 자동 scaffold

---

## 5.3 `VihariKanukollu/browzy.ai`

### 저장소
- [browzy.ai](https://github.com/VihariKanukollu/browzy.ai)

### 읽을 파일 순서
1. `README.md`
2. `src/core/ingest/*`
3. `src/core/compile/*`
4. `src/core/query/*`
5. `src/core/lint/*`
6. `src/core/retrieval/*`
7. `src/core/discovery/crystallizer.ts`
8. `activityLog.ts`

### 왜 읽는가
- 질문 중 발생한 새 인사이트를 draft로 다시 남기는 흐름이 좋다.
- CLI UX가 직관적이다.

### 읽고 나서 얻어야 할 것
- query -> draft file-back 방식
- activity log 운영 아이디어

---

## 5.4 `Hosuke/llmbase`

### 저장소
- [llmbase](https://github.com/Hosuke/llmbase)

### 읽을 파일 순서
1. `README.md`
2. `CLAUDE.md`
3. `config.yaml`
4. `tools/compile.py`
5. `tools/query.py`
6. `tools/lint.py`
7. `tools/worker.py`

### 왜 읽는가
- 자율 worker와 health persistence를 확인하기 좋다.
- 장기적으로 자동 유지보수 워커를 둘 때 참고된다.

### 읽고 나서 얻어야 할 것
- scheduled maintenance worker
- health report persisted 패턴
- 외부 구현에서 사용한 model fallback 발상

---

## 6. 4차 필독 순서: 보조 레퍼런스

## 6.1 `bashiraziz/llm-wiki-template`

### 저장소
- [llm-wiki-template](https://github.com/bashiraziz/llm-wiki-template)

### 읽을 파일 순서
1. `README.md`
2. `adapters/generic/WIKI-SCHEMA.md`
3. `adapters/codex/AGENTS.md`
4. `docs/sqlite-explainer.md`
5. `scripts/export-session.py`
6. `scripts/index-sessions.sh`
7. `scripts/recall.sh`

### 왜 읽는가
- 세션 대화를 검색 가능한 메모리로 만드는 구조가 잘 보인다.

### 읽고 나서 얻어야 할 것
- sessions.db
- transcript recall
- formal wiki와 chat memory 분리 방식

---

## 6.2 `Ar9av/obsidian-wiki`

### 저장소
- [obsidian-wiki](https://github.com/Ar9av/obsidian-wiki)

### 읽을 파일 순서
1. `README.md`
2. `AGENTS.md`
3. `.skills/wiki-ingest/SKILL.md`
4. `.skills/wiki-query/SKILL.md`
5. `.skills/wiki-lint/SKILL.md`
6. `.skills/wiki-status/SKILL.md`
7. `.skills/wiki-update/SKILL.md`
8. `.skills/cross-linker/SKILL.md`

### 왜 읽는가
- 여러 에이전트에 같은 위키 프로토콜을 먹이는 방법을 보여준다.

### 읽고 나서 얻어야 할 것
- manifest 기반 delta tracking
- cross-link automation
- multi-agent skill pack 구조

---

## 6.3 `mpazik/Binder`

### 저장소
- [Binder](https://github.com/mpazik/Binder)

### 읽을 파일 순서
1. `README.md`
2. `.binder/types.yaml`
3. query 관련 문서
4. transaction log 관련 문서
5. editor/LSP/MCP 설명 문서

### 왜 읽는가
- 규모가 커졌을 때 왜 파일 기반 인덱스만으로 힘들어지는지 이해하게 해준다.

### 읽고 나서 얻어야 할 것
- structured query 필요성
- transaction log 기반 사고방식
- 장기 확장 그림

---

## 7. 빠르게 읽는 1일 코스

시간이 부족하면 아래 순서만 읽어도 된다.

1. [Karpathy gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)
2. `atomic-knowledge/AGENT.md`
3. `atomic-knowledge/docs/CANDIDATE_LIFECYCLE.md`
4. `llm-knowledge-base/docs/learning-layer.md`
5. `sage-wiki/README.md`
6. `sage-wiki/internal/compiler/pipeline.go`
7. `llm-wiki-template/docs/sqlite-explainer.md`
8. `memex/docs/architecture.md`

이 순서면 다음 4가지를 확보할 수 있다.
- 왜 raw/wiki/schema가 필요한지
- 왜 candidate layer가 필요한지
- 왜 learning layer가 꼭 필요한지
- 실제 구현을 어떤 모듈로 나눌지

---

## 8. 팀 내 분업용 읽기 분배

### 기획 담당
- Karpathy gist
- `atomic-knowledge`
- `llm-knowledge-base`
- `mnemon`

### 백엔드 담당
- `sage-wiki`
- `memex`
- `llm-wiki-template`
- `Binder`

### 프론트엔드 담당
- `sage-wiki` web UI
- `llmbase`
- `llm-fandom`

### AI/프롬프트 담당
- `memex/docs/prompts.md`
- `atomic-knowledge/AGENT.md`
- `Ar9av/obsidian-wiki` skill files

---

## 9. 읽으면서 반드시 체크할 질문

모든 레퍼런스를 읽을 때 아래 질문에 답을 붙여가며 읽는 것이 좋다.

1. 이 구조는 raw source를 어떻게 보존하는가?
2. 미완성 지식은 어디에 저장하는가?
3. 답변 결과가 어떻게 다시 지식으로 남는가?
4. stale 정보와 잘못된 정보를 어떻게 관리하는가?
5. 학생 개인화는 어떤 계층에서 처리하는가?
6. 규모가 커졌을 때 검색은 어떻게 버티는가?
7. 사람 승인 지점은 어디에 있는가?

---

## 10. 최종 추천 정독 순서

정말 한 줄로 줄이면 이 순서가 가장 좋다.

1. `Karpathy gist`
2. `atomic-knowledge`
3. `llm-knowledge-base`
4. `mnemon`
5. `sage-wiki`
6. `memex`
7. `llm-wiki-template`
8. `Binder`

이 순서대로 읽으면,
- 철학
- 지식 모델
- 학습 개입
- 개인화
- 구현
- 운영
- 세션 메모리
- 확장성

까지 자연스럽게 이어진다.

---

## 11. 한 줄 결론

우리가 참고해야 할 것은 “가장 화려한 데모”가 아니라,

`candidate를 어떻게 다루는지`
`답변을 어떻게 다시 위키에 남기는지`
`자동 정리를 실제 학습으로 어떻게 연결하는지`

이 세 가지를 가장 잘 설명하는 레퍼런스다.
