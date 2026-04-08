# Knowloop MVP 차용 패턴

## 1. 목적

이 문서는 조사한 구현 저장소들 중 어떤 패턴을 현재 Knowloop MVP에 차용할지 정리한 표이다.

원칙은 단순하다.

- `그대로 복제하지 않는다`
- `검증된 패턴만 필요한 만큼 가져온다`
- `현재 MVP에서 구현 가능한 범위만 채택한다`

---

## 2. 최종 MVP 정의

MVP의 한 줄 정의:

`학생의 AI 학습 대화와 강의자료를 축적 가능한 학습 위키로 변환하고, 교강사에게 반복 오개념과 개입 포인트를 보여주는 교육용 AI Memory OS`

MVP 핵심 사용자:
- 수강생
- 교강사

운영자 기능은 최소화:
- 공지/FAQ 후보 생성 정도만 포함

---

## 3. 기능별 차용 정리표

| MVP 기능 | 사용자 가치 | 차용할 패턴 | 출처 저장소 | 구현 난이도 | MVP 채택 여부 |
|---|---|---|---|---|---|
| Raw source 저장소 | 원본 보존, 출처 추적 | raw source 분리 구조 | `memex`, `atomic-knowledge`, `sage-wiki` | 하 | 채택 |
| Session memory 검색 | 예전 질문/답변 다시 찾기 | `sessions/` + SQLite FTS5 | `llm-wiki-template`, `browzy.ai` | 하 | 채택 |
| Candidate buffer | 미완성 지식과 오개념 후보 격리 | `open -> promoted/merged/dropped` | `atomic-knowledge` | 중 | 채택 |
| Formal wiki 생성 | 과목 개념/FAQ/오개념 정리 | compile pipeline | `sage-wiki`, `engram` | 중 | 채택 |
| Learning layer | 자동 요약을 실제 학습으로 연결 | gaps, flashcards, review queue | `llm-knowledge-base`, `mnemon` | 중 | 채택 |
| Instructor insight 뷰 | 반복 질문/오개념 파악 | 반 전체 candidate aggregation | `atomic-knowledge`, `browzy.ai` | 중 | 채택 |
| Write-back loop | 답변이 축적 자산이 되게 함 | query 결과 file-back | `browzy.ai`, `sage-wiki`, `memex` | 중 | 채택 |
| Lint/health 점검 | stale 정보, 고아 항목 탐지 | health / lint workflow | `sage-wiki`, `rock-star-skills`, `llmbase` | 중 | 채택 |
| Graph UI | 개념 연결 시각화 | ontology / graph | `sage-wiki` | 중상 | 선택 |
| Validator gate | 후보 지식 승격 통제 | human validation gate | `atomic-knowledge`, `pnakamura gist` | 중 | 채택 |
| Audit log | 변경 이력과 책임 추적 | audit log / queue | `memex`, `Binder` | 중상 | 부분 채택 |
| Structured query DSL | 수백 페이지 이상 검색 고도화 | DB-first query model | `Binder` | 상 | 후순위 |

---

## 4. Repo별 채택 전략

| 저장소 | 가져올 것 | 안 가져올 것 | 이유 |
|---|---|---|---|
| `Nimo1987/atomic-knowledge` | candidate lifecycle, active/recent/index, lint discipline | 전체 프로토콜을 그대로 복제 | 교육용 지식 품질 관리에 가장 적합 |
| `xoai/sage-wiki` | compile/query/lint 구조, hybrid search 사고방식, UI 아이디어 | 무거운 전체 stack 그대로 도입 | 제품형 흐름 참고 가치가 큼 |
| `wastedcode/memex` | wiki별 직렬 queue, audit log 사고방식 | Linux 격리 런타임 전체 | 운영 안정성은 좋지만 MVP엔 과함 |
| `arturseo-geo/llm-knowledge-base` | learning layer, flashcards, gap tracking | 전체 문서 체계 그대로 | 교육 솔루션에 가장 직접적 |
| `bashiraziz/llm-wiki-template` | session export/search 구조 | adapter 복잡도 전체 | 대화 로그 검색에 즉효 |
| `VihariKanukollu/browzy.ai` | 질문 중 insight draft 생성 | 터미널 중심 전체 UX | 학생 개인 write-back에 유용 |
| `dkushnikov/mnemon` | reader-context 기반 개인화 | full extraction engine 전부 | 학생별 개인화에 적합 |
| `mpazik/Binder` | transaction/audit 사고방식 | DB-first 전체 구조 | 장기 확장에는 중요하지만 MVP는 과설계 |
| `Hosuke/llmbase` | worker, health persisted 패턴 | 풀스택 전체 | 장기 자동화 참고용 |

---

## 5. 실제 MVP 기능 명세

## 5.1 수강생 기능

### 기능 A. AI 학습 대화 자동 저장 및 검색

설명:
- 학생이 AI에게 한 질문과 답변을 `session memory`에 저장
- 과거 질문 검색 가능

차용:
- `llm-wiki-template`
- `browzy.ai`

구현 방식:
- `sessions.db`에 role, student_id, course_id, question, answer, tags, created_at 저장
- FTS5로 빠른 회수

### 기능 B. 개인 학습 위키 자동 생성

설명:
- 질문/답변을 그대로 저장하지 않고
- 개념, 헷갈린 이유, 다음 복습 포인트 중심으로 재구성

차용:
- `mnemon`
- `llm-knowledge-base`

구현 방식:
- `learning/students/{id}/profile.md`
- `gaps.md`
- `review_queue.md`
- `flashcards.md`

### 기능 C. 약점 개념 자동 추출

설명:
- 반복 질문과 오답 패턴으로 약점 개념을 추출

차용:
- `atomic-knowledge`
- `llm-knowledge-base`

구현 방식:
- candidate에 잠정 오개념 적재
- 반복되면 learning layer에 gap으로 반영

### 기능 D. 다음 학습 액션 제안

설명:
- 복습 카드
- 미니 퀴즈
- 다음에 물어볼 질문 추천

차용:
- `llm-knowledge-base`

구현 방식:
- gap 기반 템플릿 생성

---

## 5.2 교강사 기능

### 기능 E. 반 전체 반복 질문 뷰

설명:
- 같은 질문이 반복되는지 확인
- 수업 중 어느 개념에서 가장 많이 막히는지 파악

차용:
- `atomic-knowledge`
- `browzy.ai`

구현 방식:
- candidate를 반 단위로 집계
- 질문 빈도와 concept 매핑

### 기능 F. 오개념 히트맵

설명:
- 반별, 단원별 흔들리는 개념 가시화

차용:
- `sage-wiki`
- `atomic-knowledge`

구현 방식:
- concept-candidate 연결 수를 기반으로 집계

### 기능 G. FAQ / 보충설명 초안 자동 생성

설명:
- 반복되는 질문을 바탕으로 공지나 보충자료 초안 생성

차용:
- `memex`
- `browzy.ai`

구현 방식:
- candidate -> 승인 -> formal wiki FAQ 승격

---

## 5.3 운영자 최소 기능

### 기능 H. 공지/FAQ 후보 정리

설명:
- 학생 문의가 반복되면 운영 FAQ 후보 생성

차용:
- `memex`
- `atomic-knowledge`

구현 방식:
- 운영 role session을 별도 저장
- FAQ candidate 생성

---

## 6. MVP에서 반드시 생략할 것

다음 항목은 좋아 보이지만 MVP에서는 빼는 것이 맞다.

1. full vector infra
- 초기에는 FTS5 + BM25면 충분

2. 복잡한 multi-agent orchestration
- 설명은 할 수 있지만 실제 구현은 단일 백엔드 파이프라인으로 시작

3. Binder식 전면 DB 전환
- 장기 확장용으로 남김

4. 완전 자동 승격
- 교육에서는 지식 오염 위험이 큼
- 교강사 승인 지점 유지

5. 거대한 graph UI
- 기본 시각화 정도면 충분
- 핵심은 graph가 아니라 학습 개입

---

## 7. MVP 우선순위 표

| 우선순위 | 기능 | 이유 |
|---|---|---|
| P0 | raw source 저장 | 출처 없는 위키는 위험함 |
| P0 | session memory 검색 | 학생 반복 질문 문제를 바로 해결 |
| P0 | candidate buffer | 위키 오염 방지 핵심 |
| P0 | formal wiki 생성 | Memory OS의 본체 |
| P0 | learning layer 최소 버전 | 자동 요약의 한계를 보완 |
| P1 | 교강사 반복 질문/오개념 대시보드 | 교육 솔루션다운 차별점 |
| P1 | lint/health 리포트 | 지속형 시스템의 품질 유지 |
| P2 | graph view | 시각적 설득력은 있으나 본질은 아님 |
| P2 | 운영자 FAQ 대시보드 고도화 | 범위 과확장 방지 |
| P3 | structured query DSL | 장기 확장 과제 |

---

## 8. 추천 MVP 조합

가장 현실적인 MVP 조합은 다음과 같다.

### 코어 구조
- `atomic-knowledge`의 candidate 레이어
- `sage-wiki`의 compile/query/lint 파이프라인
- `llm-wiki-template`의 sessions FTS 검색

### 학습 개입
- `llm-knowledge-base`의 review/gap/flashcard 설계
- `mnemon`의 reader-context 개인화

### 운영 안정성
- `memex`의 audit/queue 사고방식 일부 차용

---

## 9. 한 줄 결론

현재 MVP는 `AI가 답변하는 것`보다 `질문과 자료가 축적되는 구조`를 먼저 보여줘야 한다.

따라서 MVP는 다음 3가지를 중심으로 설계하는 것이 가장 강하다.

1. 학생 질문을 사라지지 않게 만드는 `session memory`
2. 미완성 지식을 안전하게 다루는 `candidate buffer`
3. 자동 정리를 실제 학습 성과로 연결하는 `learning layer`
