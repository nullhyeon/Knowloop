# Knowloop

> 질문이 쌓일수록 더 정리되는 수업 지식 운영 시스템

Knowloop는 교육 현장의 질문, 강의 자료, 후보 지식을 함께 운영하는 `LLM-Wiki` 기반 Edu Memory OS입니다.
단순히 답변만 하는 챗봇이 아니라, 질문을 세션으로 축적하고, 학습 노트와 후보 지식을 만들고, 검토를 거쳐 공식 위키를 갱신합니다.

---

## 해결하는 문제

교육 현장에서는 같은 문제가 반복됩니다.

- 학생은 AI에게 질문하고 답을 받지만, 그 내용이 다음 학습으로 잘 이어지지 않습니다.
- 교강사는 같은 질문을 여러 번 다시 설명하지만, 그 흐름이 공식 지식으로 정리되지 않습니다.
- 운영 정보와 수업 정보가 분리돼 있어, 공지와 FAQ도 계속 다시 만들어야 합니다.

Knowloop는 이 문제를 `질문 -> 축적 -> 검토 -> 승격 -> 탐색` 흐름으로 해결합니다.

---

## 핵심 경험

### 1. Ask
- 학생은 현재 수업 맥락에서 질문합니다.
- 답변만 보이는 것이 아니라, 근거, 참조 위키, write-back 결과가 함께 보입니다.

### 2. Learning
- 질문은 학습 노트, gap tracker, next actions로 이어집니다.
- 학생은 "무엇을 다시 봐야 하는지"를 바로 확인할 수 있습니다.

### 3. Review
- 불확실한 내용은 바로 공식 지식이 되지 않습니다.
- candidate를 만들고, 교강사나 검토자가 patch preview를 본 뒤 approve / merge / drop 합니다.

### 4. Wiki
- 검토를 통과한 내용만 공식 위키로 승격됩니다.
- 공식 위키는 source refs, candidate refs, updated_at을 함께 보여주는 maintained knowledge layer입니다.

### 5. Insights
- 교강사는 반복 질문, 오개념 패턴, 우선순위 액션을 한 화면에서 봅니다.
- 단순 차트보다 "다음 수업에서 무엇을 해야 하는가"가 먼저 보이도록 설계했습니다.

---

## 주요 사용자

### 학생
- Ask에서 질문
- Learning에서 confusion, gaps, next actions 확인
- Wiki에서 공식 개념 문서 탐색

### 교강사
- Insights에서 반복 질문과 오개념 패턴 확인
- Review에서 candidate 검토
- Wiki와 Sources에서 공식 지식과 근거 추적

### 보조 역할
- `operator`: 운영 자료와 operations domain 관리
- `validator`: candidate 검토와 maintenance 확인

MVP의 중심 경험은 `학생`과 `교강사`에 맞춰 설계되어 있습니다.

---

## 핵심 기능

| 기능 | 설명 |
| --- | --- |
| Context bootstrap | role / course / class / domain 맥락을 기준으로 같은 제품 안에서 다른 사용자 경험을 제공합니다. |
| Query + evidence | 답변과 함께 answer basis, retrieval refs, runtime 상태, write-back 결과를 보여줍니다. |
| Learning layer | learning note, gaps, next actions, related wiki를 학생 개인 흐름으로 제공합니다. |
| Candidate workflow | 불확실한 지식은 candidate로 저장하고 review를 거쳐 formal wiki로 승격합니다. |
| Wiki browser | 공식 지식을 탐색하고 source refs, candidate refs, scope를 함께 확인할 수 있습니다. |
| Instructor insights | 반복 confusion 패턴, 우선 review 액션, 수업 개입 포인트를 보여줍니다. |
| Source registry | 자료 등록, scope 관리, linked wiki / candidate traceability를 지원합니다. |
| Maintenance console | stale candidate, orphan refs, report status를 운영 관점에서 확인합니다. |

---

## AI 활용 전략

Knowloop는 `결정론적 로직`과 `생성형 AI`를 분리합니다.

### 1. 결정론적 레이어
- session 저장
- candidate lifecycle
- review state transition
- audit trail
- maintenance report

이 레이어는 재현성과 회복성을 위해 deterministic하게 유지합니다.

### 2. 생성형 레이어
- grounded answer rewrite
- 학습 노트/후보 지식 생성 보조
- 위키 중심 답변 보정

현재 런타임은 OpenAI 기반 optional adapter를 사용합니다.

핵심 원칙:
- 공식 지식은 wiki 우선
- raw source는 fallback
- 검토되지 않은 내용은 formal wiki로 직접 쓰지 않음
- AI 출력은 candidate / review / audit 흐름 안에서만 승격

---

## 현재 구현 상태

### 프론트
- `/` 첫 시작 화면
- `/workspace`
- `/ask`
- `/learning`
- `/wiki`
- `/review`
- `/insights`
- `/sources`
- `/maintenance`

### 백엔드
- `context`
- `query`
- `learning`
- `review`
- `sessions`
- `sources`
- `wiki`
- `instructor insights`
- `maintenance`

### 실제 API 연결 완료 surface
- `/workspace`
- `/ask`
- `/learning`
- `/wiki`
- `/review`
- `/sources`
- `/maintenance`
- `/insights`

현재 표면은 실제 API 계약 위에서 동작해야 하며, 정적 demo seed/profile 흐름은 운영 계약에서 제거되었습니다.

---

## 서비스 시작 방식

프론트엔드는 운영 환경에서 인증 또는 trusted signed-context adapter를 통해
역할, actor, course, class, domain을 설정한 뒤 각 surface로 진입해야 합니다.
`X-Knowloop-Profile-Id` 기반 샘플 프로필 전환은 더 이상 런타임 계약이 아닙니다.

---

## 기술 스택

| 영역 | 기술 |
| --- | --- |
| Frontend | Next.js 16, React 19, TypeScript, Tailwind CSS v4 |
| Backend | FastAPI, Python 3.12 |
| Runtime AI | OpenAI API (`gpt-5.4`) |
| Storage | SQLite + Markdown/files under `data/` |
| Knowledge layers | raw / session / candidate / wiki / learning / maintenance |
| Validation | pytest, ruff, ESLint, Next build |
| Tooling | `uv`, PowerShell scripts |

---

## 저장 구조

Knowloop는 현재 backend-first MVP로, 파일 기반 지식 저장과 SQLite 기반 메타 저장을 함께 사용합니다.

- raw sources: `data/raw`
- sessions: `data/sessions`, `data/meta/sessions.db`
- candidates: `data/candidate`
- wiki: `data/wiki`
- learning: `data/learning`
- audit / manifest / maintenance: `data/meta`

---

## 빠른 시작

### 1. 의존성 설치

```powershell
cd Knowloop
.\scripts\bootstrap.ps1
```

### 2. 백엔드 실행

```powershell
cd Knowloop
.\scripts\dev-api.ps1
```

### 3. 프론트 실행

```powershell
cd Knowloop\apps\web
npm install
npm run dev
```

### 4. 검증

```powershell
cd Knowloop
.\scripts\test-api.ps1
.\scripts\lint-api.ps1
.\scripts\smoke-api.ps1
```

프론트 검증:

```powershell
cd Knowloop\apps\web
npm run lint
npm run build
```

## 문서

핵심 문서:

- [`docs/README.md`](docs/README.md)
- [`docs/product/product-overview.md`](docs/product/product-overview.md)
- [`docs/product/mvp-scope.md`](docs/product/mvp-scope.md)
- [`docs/product/role-permissions.md`](docs/product/role-permissions.md)
- [`docs/architecture/api-contracts.md`](docs/architecture/api-contracts.md)
- [`docs/architecture/data-contracts.md`](docs/architecture/data-contracts.md)
- [`docs/development/backend-runbook.md`](docs/development/backend-runbook.md)
- [`DESIGN.md`](DESIGN.md)
- [`SITE.md`](SITE.md)

---

## 작업 방식

Knowloop는 AI를 단순 자동완성이 아니라 협업 구조로 사용합니다.

- `Codex Builder`: 구현
- `Codex Critic`: 정보 구조와 경계 점검
- `Codex Reviewer`: 코드와 동작 검토

프론트와 백엔드 모두 작은 슬라이스 단위로 구현하고, 테스트 가능한 상태로 닫는 방식을 기본 원칙으로 삼습니다.

---

## 한 줄 요약

Knowloop는 `학생 질문을 사라지지 않는 지식으로 바꾸고, 교강사가 그것을 검토해 공식 위키로 운영하는 교육용 LLM-Wiki 시스템`입니다.
