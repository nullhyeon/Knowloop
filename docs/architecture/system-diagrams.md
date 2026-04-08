# Knowloop 시스템 다이어그램

## 1. 문서 목적

이 문서는 Knowloop(`Edu Memory OS`)의 핵심 구조를 다이어그램으로 정리한 문서이다.

참고:
- 이 문서는 전체 제품 구조와 목표 워크플로를 설명한다.
- 현재 MVP 시연 기준은 `docs/product/mvp-scope.md`, `docs/product/evaluation-plan.md`, `docs/product/demo-script.md`를 우선한다.

포함 범위는 다음과 같다.

- Use Case Diagram
- Data Flow Diagram
- Sequence Diagram

모든 다이어그램은 Mermaid 형식으로 작성했으며, 발표자료와 문서에 바로 옮겨 사용할 수 있다.

---

## 2. Use Case Diagram

### 2.1 전체 사용자-기능 관계

```mermaid
flowchart LR
    student[수강생]
    instructor[교강사]
    operator[교육 운영자]
    validator[검토자 / 관리자]

    subgraph system["Edu Memory OS"]
        uc1(질문하고 맞춤형 답변 받기)
        uc2(개인 학습 위키 자동 생성)
        uc3(약점 개념 및 복습 큐 확인)
        uc4(반복 질문 및 오개념 분석 보기)
        uc5(보충설명 / FAQ 초안 생성)
        uc6(운영 FAQ / 공지 후보 정리)
        uc7(공지 충돌 및 반복 문의 탐지)
        uc8(candidate 검토 및 위키 승격)
        uc9(학습 / 수업 / 운영 위키 검색)
    end

    student --> uc1
    student --> uc2
    student --> uc3
    student --> uc9

    instructor --> uc4
    instructor --> uc5
    instructor --> uc9

    operator --> uc6
    operator --> uc7
    operator --> uc9

    validator --> uc8
    validator --> uc9

    uc1 --> uc2
    uc1 --> uc3
    uc4 --> uc5
    uc6 --> uc7
    uc8 --> uc9
```

### 2.2 해설

- 수강생은 질문응답으로 끝나는 것이 아니라 `개인 학습 위키`, `약점 개념`, `복습 큐`까지 이어진다.
- 교강사는 단순히 질문을 받는 것이 아니라 `반복 질문`, `오개념`, `개입 포인트`를 확인한다.
- 교육 운영자는 `FAQ`, `공지`, `반복 문의`를 구조적으로 관리한다.
- 검토자 또는 관리자는 candidate를 정식 위키로 승격하는 품질 관리 역할을 맡는다.

---

## 3. Data Flow Diagram

## 3.1 Context Level Data Flow Diagram

```mermaid
flowchart LR
    student[수강생]
    instructor[교강사]
    operator[교육 운영자]

    system([Edu Memory OS])

    student -->|질문, 학습 대화, 과제 메모| system
    instructor -->|강의자료, 피드백, 개입 승인| system
    operator -->|공지, 상담 메모, 운영 문의| system

    system -->|맞춤형 답변, 개인 학습 위키, 복습 큐| student
    system -->|오개념 분석, 반복 질문 리포트, FAQ 초안| instructor
    system -->|운영 FAQ, 공지 충돌 알림, 반복 문의 정리| operator
```

### 의미

- 외부 사용자 3종이 시스템에 서로 다른 데이터를 제공한다.
- 시스템은 각 역할에 맞는 결과물을 되돌려준다.
- 핵심은 모든 입력이 단순 저장이 아니라 `지속형 메모리`로 축적된다는 점이다.

---

## 3.2 Internal Data Flow Diagram

```mermaid
flowchart LR
    raw[외부 입력 데이터]
    ingest([Ingest Engine])
    session([Session Memory Manager])
    candidate([Candidate Builder])
    validator([Validation / Approval])
    wiki([Formal Wiki Builder])
    learning([Learning Layer Builder])
    lint([Lint / Health Checker])
    query([Query Engine])

    raw_store[(Raw Sources)]
    session_store[(Sessions DB)]
    candidate_store[(Candidate Store)]
    wiki_store[(Formal Wiki)]
    learning_store[(Learning Layer)]
    meta_store[(Manifest / Audit / Health)]

    raw --> ingest
    ingest --> raw_store
    ingest --> session
    ingest --> candidate

    session --> session_store
    candidate --> candidate_store
    candidate --> validator
    validator --> wiki
    wiki --> wiki_store
    wiki --> learning
    learning --> learning_store

    wiki_store --> query
    session_store --> query
    learning_store --> query
    candidate_store --> query

    query --> student_out[학생 응답]
    query --> instructor_out[교강사 인사이트]
    query --> operator_out[운영 인사이트]

    wiki_store --> lint
    candidate_store --> lint
    session_store --> lint
    lint --> meta_store
    lint --> wiki_store
```

### 의미

- `Raw Sources`는 원본 데이터 저장소다.
- `Session Memory`는 검색 가능한 대화 메모리다.
- `Candidate Store`는 아직 확정되지 않은 지식을 저장한다.
- `Formal Wiki`는 검토를 거친 공식 지식층이다.
- `Learning Layer`는 학생 개인 복습과 이해 강화를 위한 레이어다.
- `Lint / Health Checker`는 위키의 무결성과 최신성을 유지한다.

---

## 4. Sequence Diagram

## 4.1 기능 1: 수강생 질문응답 및 개인 학습 위키 갱신

```mermaid
sequenceDiagram
    actor Student as 수강생
    participant UI as 웹앱
    participant Query as Query Engine
    participant Session as Session Memory
    participant Wiki as Formal Wiki
    participant Learning as Learning Layer
    participant Candidate as Candidate Builder

    Student->>UI: 개념 질문 입력
    UI->>Query: 질문 전달
    Query->>Session: 이전 질문/대화 검색
    Session-->>Query: 관련 대화 반환
    Query->>Wiki: 관련 개념 / FAQ / 오개념 검색
    Wiki-->>Query: 관련 문서 반환
    Query-->>UI: 맥락 기반 답변 생성
    UI-->>Student: 답변 표시

    Query->>Candidate: 새 오개념/미해결 질문 후보 생성
    Candidate-->>Query: 후보 저장 완료
    Query->>Learning: 개인 학습 위키 / gaps / review queue 갱신
    Learning-->>Query: 갱신 완료
```

### 핵심 포인트

- 질문은 답변으로 끝나지 않는다.
- 시스템은 동시에 `candidate`와 `learning layer`를 갱신한다.

---

## 4.2 기능 2: 반복 질문 누적으로 오개념 후보 생성

```mermaid
sequenceDiagram
    actor Student as 수강생
    participant UI as 웹앱
    participant Query as Query Engine
    participant Session as Session Memory
    participant Candidate as Candidate Store
    participant Analyzer as Misconception Analyzer

    Student->>UI: 유사한 개념 다시 질문
    UI->>Query: 질문 전달
    Query->>Session: 기존 질문 이력 조회
    Session-->>Query: 유사 질문 다수 반환
    Query->>Analyzer: 반복 패턴 분석 요청
    Analyzer->>Candidate: 잠정 오개념 후보 등록
    Candidate-->>Analyzer: 저장 완료
    Analyzer-->>Query: 오개념 가능성 반환
    Query-->>UI: 기존 질문과 연결한 설명 제공
    UI-->>Student: 답변 + 복습 추천 표시
```

### 핵심 포인트

- 시스템은 단순히 “또 답변”하는 것이 아니라 `반복 패턴`을 감지한다.
- 반복 질문은 `candidate`를 통해 오개념 후보로 승격된다.

---

## 4.3 기능 3: 교강사 강의자료 업로드 후 위키 자동 갱신

```mermaid
sequenceDiagram
    actor Instructor as 교강사
    participant UI as 웹앱
    participant Ingest as Ingest Engine
    participant Raw as Raw Sources
    participant Candidate as Candidate Builder
    participant Wiki as Formal Wiki Builder
    participant Learning as Learning Layer Builder
    participant Meta as Manifest / Log

    Instructor->>UI: 강의자료 업로드
    UI->>Ingest: 파일 전달
    Ingest->>Raw: 원본 저장
    Raw-->>Ingest: 저장 완료
    Ingest->>Wiki: 관련 개념 / FAQ / 주차 요약 업데이트 요청
    Wiki-->>Ingest: 위키 초안 생성
    Ingest->>Candidate: 예상 오개념 / 질문 후보 생성
    Candidate-->>Ingest: 후보 저장
    Ingest->>Learning: 학생 복습 포인트 업데이트 요청
    Learning-->>Ingest: 학습 레이어 갱신
    Ingest->>Meta: manifest / log 업데이트
    Meta-->>Ingest: 기록 완료
    Ingest-->>UI: 처리 완료
    UI-->>Instructor: 위키 갱신 결과 표시
```

### 핵심 포인트

- 강의자료는 단순 업로드 파일로 끝나지 않는다.
- 위키, 오개념 후보, 복습 포인트, 로그까지 함께 갱신된다.

---

## 4.4 기능 4: 교강사 오개념 대시보드 조회 및 candidate 승격

```mermaid
sequenceDiagram
    actor Instructor as 교강사
    participant UI as 대시보드
    participant Analytics as Insight Aggregator
    participant Candidate as Candidate Store
    participant Wiki as Formal Wiki
    participant Validator as Approval Flow

    Instructor->>UI: 오개념 대시보드 조회
    UI->>Analytics: 반 전체 후보 집계 요청
    Analytics->>Candidate: 반복 질문 / 오개념 후보 조회
    Candidate-->>Analytics: 후보 목록 반환
    Analytics-->>UI: 히트맵 / 우선순위 제공
    UI-->>Instructor: 반복 오개념 시각화

    Instructor->>UI: 특정 후보를 FAQ로 승격 승인
    UI->>Validator: 승격 요청
    Validator->>Wiki: FAQ / 오개념 페이지 업데이트
    Wiki-->>Validator: 반영 완료
    Validator-->>UI: 승격 완료
    UI-->>Instructor: 반영 결과 표시
```

### 핵심 포인트

- 교강사는 분석 결과를 보기만 하는 것이 아니라 `승인`을 통해 공식 위키를 갱신한다.
- 이 승인이 지식 품질을 유지하는 핵심 장치다.

---

## 4.5 기능 5: 교육 운영자 문의 분석 및 운영 FAQ 생성

```mermaid
sequenceDiagram
    actor Operator as 교육 운영자
    participant UI as 운영 화면
    participant Ingest as Ingest Engine
    participant Session as Session Memory
    participant Candidate as Candidate Store
    participant Wiki as Operations Wiki
    participant Lint as Conflict Checker

    Operator->>UI: 문의 내역 / 공지 등록
    UI->>Ingest: 데이터 전달
    Ingest->>Session: 문의 / 상담 기록 저장
    Session-->>Ingest: 저장 완료
    Ingest->>Candidate: 반복 문의 FAQ 후보 생성
    Candidate-->>Ingest: 후보 저장
    Ingest->>Lint: 공지 충돌 / 누락 여부 검사
    Lint-->>Ingest: 충돌 결과 반환
    Ingest->>Wiki: 운영 FAQ 초안 업데이트
    Wiki-->>Ingest: 위키 갱신 완료
    Ingest-->>UI: 결과 반환
    UI-->>Operator: FAQ 후보 + 충돌 알림 표시
```

### 핵심 포인트

- 운영 영역도 동일한 패턴으로 동작한다.
- 문의는 세션 메모리로 저장되고, 반복되면 운영 FAQ 후보가 된다.

---

## 4.6 기능 6: Lint / Health Check 및 유지보수 루프

```mermaid
sequenceDiagram
    participant Scheduler as Scheduler
    participant Lint as Lint Engine
    participant Candidate as Candidate Store
    participant Wiki as Formal Wiki
    participant Meta as Health Store
    actor Instructor as 교강사

    Scheduler->>Lint: 정기 점검 실행
    Lint->>Candidate: stale / 미승격 후보 점검
    Candidate-->>Lint: 후보 상태 반환
    Lint->>Wiki: orphan / broken link / source drift 점검
    Wiki-->>Lint: 위키 상태 반환
    Lint->>Meta: health score / review queue 저장
    Meta-->>Lint: 저장 완료
    Lint-->>Instructor: 검토 필요 항목 알림
```

### 핵심 포인트

- Memory OS는 생성만 하는 시스템이 아니다.
- 유지보수와 건강 상태 점검이 있어야 지속 가능한 위키가 된다.

---

## 5. 발표 시 강조 포인트

다이어그램을 발표자료에 사용할 때는 다음 흐름으로 설명하는 것이 좋다.

1. `Use Case Diagram`
- 누가 이 서비스를 쓰는지
- 학생, 교강사, 운영자가 각각 어떤 실질적 문제를 해결하는지

2. `Context DFD`
- 왜 이 서비스가 단순 챗봇이 아닌지
- 입력과 출력이 역할별로 다르다는 점

3. `Internal DFD`
- raw -> session -> candidate -> wiki -> learning 구조가 핵심이라는 점

4. `Sequence Diagram`
- 질문 후 답변만 나오는 것이 아니라
- 위키, 후보 지식, 학습 레이어가 함께 갱신된다는 점

---

## 6. 한 줄 결론

본 서비스의 본질은 `질문에 답하는 AI`가 아니라, `질문과 수업과 운영의 상호작용을 축적 자산으로 바꾸는 교육 Memory OS`이며, 위 다이어그램들은 그 구조를 시각적으로 설명하기 위한 핵심 자료이다.
