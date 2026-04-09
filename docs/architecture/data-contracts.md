# Knowloop 데이터 계약

## 1. 문서 목적

이 문서는 Knowloop MVP 구현에 필요한 데이터 계약을 고정하기 위한 문서다.

이 문서에서 정하는 범위는 다음과 같다.

- 핵심 엔터티 정의
- 식별자(ID) 규칙
- 필수 메타데이터
- 파일명 및 경로 규칙
- 시간, 상태, 참조 방식의 공통 규칙

목표는 구현 단계에서 “이 데이터는 어디에 저장해야 하지?”, “이 ID는 어떤 형식이어야 하지?” 같은 추측을 없애는 것이다.

---

## 2. 데이터 계약의 기본 원칙

1. 모든 주요 산출물은 추적 가능해야 한다.
- 어떤 질문에서 나왔는지
- 어떤 source를 참조했는지
- 어떤 후보에서 승격되었는지

2. raw, session, candidate, wiki, learning은 분리한다.
- 한 레이어의 책임을 다른 레이어가 대신하지 않는다.

3. ID는 사람이 읽을 수 있어야 하고, 경로는 예측 가능해야 한다.
- 디버깅과 수동 검토가 가능해야 한다.

4. 시간은 전부 UTC 기준으로 저장한다.
- 포맷은 ISO 8601 또는 `YYYYMMDDTHHMMSSZ`를 사용한다.

5. MVP에서는 복잡한 정규화보다 명시성과 안정성을 우선한다.

---

## 3. 공통 규칙

### 3.1 슬러그 규칙

- 영문 소문자
- 단어 구분은 `-`
- 공백, 한글, 특수문자는 슬러그에 직접 넣지 않는다

예시:
- `limits-introduction`
- `week-03-derivatives`
- `repeated-chain-rule-question`

### 3.2 시간 규칙

사람이 읽는 메타데이터:
- `2026-04-08T10:30:00Z`

파일명/ID suffix:
- `20260408T103000Z`

### 3.3 역할 값

MVP에서 허용하는 역할 값은 다음과 같다.

- `student`
- `instructor`
- `operator`
- `validator`
- `system`

### 3.4 공통 상태 값

현재 MVP에서 주로 쓰는 상태 값은 다음과 같다.

- `registered`
- `open`
- `promoted`
- `merged`
- `dropped`
- `failed`

각 엔터티는 필요한 값만 선택해서 사용한다.

---

## 4. 핵심 식별자 규칙

## 4.1 사용자 계열 ID

MVP에서는 외부 인증 연동 대신 repository-safe fixture 기준 ID를 사용한다.

형식:
- 학생: `stu-<slug-or-seq>`
- 교강사: `ins-<slug-or-seq>`
- 운영자: `ops-<slug-or-seq>`
- 검토자: `val-<slug-or-seq>`

예시:
- `stu-kim-minji`
- `ins-calculus-team`
- `ops-academic-office`
- `val-course-admin`

원칙:
- 공개 저장소에서는 실명 대신 가명 fixture 사용
- 실제 서비스 전환 시에도 내부 canonical id는 별도 매핑 가능하도록 분리

## 4.2 과목 및 반 ID

형식:
- `course-<slug>`
- `class-<course-slug>-<term>-<section>`

예시:
- `course-calculus-1`
- `class-calculus-1-2026-spring-a`

원칙:
- `course_id`는 과목 자체
- `class_id`는 실제 운영 반 단위
- MVP 구현에서는 대부분 `class_id` 기준 집계를 우선한다

## 4.3 원본 source ID

형식:
- `src-<source-type>-<class-slug>-<slug>-<timestamp>`

예시:
- `src-lecture-note-class-calculus-1-2026-spring-a-week-03-20260408T103000Z`
- `src-student-question-class-calculus-1-2026-spring-a-chain-rule-confusion-20260408T110500Z`

원칙:
- source는 등록 후 ID를 바꾸지 않는다
- 제목이 바뀌어도 `source_id`는 고정한다

## 4.4 session ID

형식:
- `ses-<role>-<user-id>-<class-slug>-<timestamp>`

예시:
- `ses-student-stu-kim-minji-class-calculus-1-2026-spring-a-20260408T111000Z`

원칙:
- MVP에서는 “질문-답변 1회 상호작용”을 1개의 session record로 본다
- 추후 thread 구조가 필요해지면 `thread_id`를 별도로 추가한다

## 4.5 candidate ID

형식:
- `cand-<kind>-<class-slug>-<slug>-<timestamp>`

예시:
- `cand-misconception-class-calculus-1-2026-spring-a-chain-rule-product-rule-mixup-20260408T112000Z`
- `cand-faq-class-calculus-1-2026-spring-a-homework-deadline-20260408T112500Z`

원칙:
- candidate는 생성 순간의 의미와 맥락을 드러내는 슬러그를 가진다
- merge되어도 원본 candidate id는 audit에서 보존한다

## 4.6 wiki page ID

형식:
- `page-<domain>-<slug>`

예시:
- `page-concepts-chain-rule`
- `page-faq-homework-submission`
- `page-misconceptions-implicit-differentiation`

원칙:
- formal wiki는 path와 page id가 거의 1:1 대응되도록 유지한다

## 4.7 learning note ID

형식:
- `learn-<student-id>-<course-slug>-<timestamp>`

예시:
- `learn-stu-kim-minji-calculus-1-20260408T113000Z`

원칙:
- learning note는 학생-과목 기준으로 생성된다
- 하나의 학생이 여러 과목을 듣더라도 과목별로 분리한다

---

## 5. 핵심 엔터티 정의

## 5.1 RawSource

정의:
- 시스템에 들어오는 원본 입력 단위

필수 필드:
- `source_id`
- `source_type`
- `domain`
- `title`
- `class_id`
- `course_id`
- `actor_role`
- `created_at`
- `origin_path`
- `checksum`
- `status`

선택 필드:
- `uploaded_by`
- `mime_type`
- `tags`
- `summary`

허용 `source_type` 예시:
- `lecture_note`
- `lecture_transcript`
- `student_question`
- `assignment_feedback`
- `announcement`
- `operations_note`
- `counseling_note`

`announcement`는 academic / operations 양쪽 domain에 존재할 수 있으므로,
`source_type`만으로는 경계를 확정하지 않고 `domain`을 함께 본다.

## 5.2 SessionRecord

정의:
- 한 번의 질문-답변 상호작용을 저장한 검색 가능한 기록

필수 필드:
- `session_id`
- `role`
- `user_id`
- `class_id`
- `course_id`
- `question`
- `answer`
- `created_at`

선택 필드:
- `tags`
- `source_refs`
- `retrieval_refs`
- `candidate_refs`
- `learning_note_refs`

MVP 원칙:
- 질문과 답변을 한 row 또는 한 record 단위로 저장한다
- 복잡한 multi-turn thread 구조는 후순위로 둔다

## 5.3 CandidateItem

정의:
- 아직 공식 지식이 아니지만 검토할 가치가 있는 구조화 후보

필수 필드:
- `candidate_id`
- `kind`
- `status`
- `title`
- `summary`
- `class_id`
- `course_id`
- `confidence`
- `source_refs`
- `created_at`

선택 필드:
- `tags`
- `merged_into`
- `approved_by`
- `approved_at`
- `related_page_id`

허용 `kind`:
- `misconception`
- `faq`
- `intervention`
- `unresolved_question`
- `operations_note`

허용 `status`:
- `open`
- `promoted`
- `merged`
- `dropped`

## 5.4 WikiPage

정의:
- 검토를 거쳐 formal wiki에 올라간 공식 지식 문서

필수 필드:
- `page_id`
- `title`
- `domain`
- `course_id`
- `class_scope`
- `updated_at`
- `source_refs`

선택 필드:
- `candidate_refs`
- `summary`
- `status`

허용 `domain` 예시:
- `concepts`
- `faq`
- `misconceptions`
- `courses`
- `operations`

MVP 원칙:
- wiki page는 markdown 문서 본문 + 최소 frontmatter 메타데이터 조합을 기본으로 한다

## 5.5 LearningNote

정의:
- 학생 개인 학습을 위해 생성되는 후속 정리 산출물

필수 필드:
- `learning_note_id`
- `student_id`
- `course_id`
- `class_id`
- `concepts`
- `gaps`
- `next_actions`
- `created_at`

선택 필드:
- `source_refs`
- `session_refs`
- `flashcards`
- `summary`

MVP 원칙:
- 이번 단계에서는 `notes`, `gaps`, `next_actions`가 우선
- `flashcards`는 스키마상 선택 필드로만 유지한다

## 5.6 AuditEvent

정의:
- 상태 변화와 주요 시스템 행동을 기록하는 감사 이벤트

필수 필드:
- `event_id`
- `entity_type`
- `entity_id`
- `action`
- `actor_role`
- `created_at`

선택 필드:
- `actor_id`
- `from_status`
- `to_status`
- `notes`

예시 action:
- `source_registered`
- `session_saved`
- `candidate_created`
- `candidate_promoted`
- `candidate_merged`
- `candidate_dropped`
- `wiki_updated`
- `learning_generated`

---

## 6. source_refs 계약

모든 candidate, wiki patch, learning note는 source traceability를 위해 `source_refs`를 가질 수 있다.

최소 구조:

```json
{
  "source_id": "src-lecture-note-class-calculus-1-2026-spring-a-week-03-20260408T103000Z",
  "source_type": "lecture_note",
  "chunk_id": "p03-c02"
}
```

원칙:
- `source_id`는 필수
- `source_type`은 필수
- `chunk_id`는 선택
- source가 하나도 없는 wiki 승격은 허용하지 않는다

---

## 7. 파일 및 경로 규칙

## 7.1 Raw Sources

경로:

```text
data/raw/<source-type>/<class-id>/<source-id>.<ext>
```

예시:

```text
data/raw/lecture-note/class-calculus-1-2026-spring-a/src-lecture-note-class-calculus-1-2026-spring-a-week-03-20260408T103000Z.md
```

## 7.2 Session Layer

MVP 기본 저장소:
- SQLite

선택적 export/debug 경로:

```text
data/sessions/<role>/<class-id>/<user-id>/<session-id>.json
```

원칙:
- canonical searchable store는 SQLite
- 파일 export는 디버깅/검수 용도

## 7.3 Candidate Layer

경로:

```text
data/candidate/<kind>/<class-id>/<candidate-id>.json
```

예시:

```text
data/candidate/misconceptions/class-calculus-1-2026-spring-a/cand-misconception-class-calculus-1-2026-spring-a-chain-rule-product-rule-mixup-20260408T112000Z.json
```

## 7.4 Formal Wiki

경로:

```text
data/wiki/<domain>/<slug>.md
```

예시:

```text
data/wiki/concepts/chain-rule.md
data/wiki/faq/homework-submission.md
data/wiki/misconceptions/implicit-differentiation.md
```

원칙:
- wiki는 페이지 성격상 경로가 안정적이어야 하므로 timestamp를 파일명에 넣지 않는다
- 변경 이력은 문서 내부 메타데이터와 audit event에서 관리한다

## 7.5 Learning Layer

경로:

```text
data/learning/students/<student-id>/<course-id>/
```

MVP 권장 파일:

```text
profile.md
notes.md
gaps.md
next_actions.md
```

추후 선택 파일:

```text
flashcards.md
review_queue.md
```

## 7.6 Meta Layer

경로:

```text
data/meta/
  manifest.json
  lint-status.json
  sessions.db
  audit.db
```

---

## 8. 필수 메타데이터 최소 집합

모든 주요 엔터티는 아래 메타데이터를 가능한 한 공통으로 가진다.

- `id`
- `created_at`
- `updated_at` 또는 `approved_at`
- `course_id`
- `class_id`
- `actor_role`
- `source_refs`

MVP에서는 완전한 정규화보다 이 공통 키들의 일관성을 우선한다.

---

## 9. 스키마와 문서의 관계

현재 JSON schema는 최소 계약을 위한 출발점이다.

연결 대상:
- `schemas/candidate_item.json`
- `schemas/wiki_patch.json`
- `schemas/learning_note.json`

이 문서는 schema보다 상위 개념 문서다.

원칙:
- 구현 스키마가 이 문서보다 약하면 스키마를 강화한다
- 구현 스키마가 이 문서와 충돌하면 먼저 이 문서를 갱신할지 검토한다

---

## 10. 이번 문서 기준으로 뒤이어 작성할 문서

이 문서를 기준으로 다음 문서가 이어져야 한다.

1. `promotion-policy.md`
- 어떤 candidate를 승격/병합/폐기할지

2. `role-permissions.md`
- 역할별 읽기/쓰기 범위

3. `evaluation-plan.md`
- 어떤 데이터 계약이 실제 데모 성공과 연결되는지

---

## 11. 한 줄 결론

Knowloop MVP의 데이터 계약은
`사람이 읽을 수 있는 ID`, `추적 가능한 source_refs`, `예측 가능한 경로`, `레이어별 분리`
이 네 가지를 중심으로 설계한다.

## 10. Flexible Domain Source Note

- `announcement` source records may exist in both `academic` and `operations` domains.
- To prevent cross-domain collisions, flexible-domain `source_id` values include a short domain token such as `acad` or `ops`.
- Raw files for flexible-domain sources are stored under `data/raw/announcement/<domain>/<class-id>/...`.
- Source title slugs are collision-resistant: Knowloop keeps a short human-readable prefix and appends a short hash suffix so non-ASCII titles and long-prefix titles do not collapse into the same `source_id`.
