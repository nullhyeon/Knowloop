# Knowloop API Contracts

## 1. 문서 목적

이 문서는 Knowloop MVP 백엔드가 제공해야 하는 HTTP API 계약을 정의한다.

이 문서의 목적은 다음과 같다.

- 프론트엔드와 백엔드가 같은 엔드포인트 모델을 따르게 한다
- Pydantic request/response 모델 설계의 기준점을 제공한다
- 역할별 권한 경계가 API 경계에도 그대로 반영되게 한다
- query, review, write-back 흐름을 라우터 단위로 고정한다

이 문서는 구현 초안이 아니라,
MVP 백엔드가 따라야 하는 제품 계약 문서다.

---

## 2. 이 문서의 위치

이 문서는 아래 문서들을 API 수준으로 연결한다.

- `docs/product/mvp-scope.md`
- `docs/architecture/data-contracts.md`
- `docs/architecture/query-writeback-policy.md`
- `docs/architecture/promotion-policy.md`
- `docs/product/role-permissions.md`

즉,

- 어떤 API가 필요한가
- 누가 어떤 API를 호출할 수 있는가
- 각 API는 무엇을 읽고 무엇을 쓰는가
- 어떤 API는 의도적으로 제공하지 않는가

를 이 문서에서 잠근다.

---

## 3. 기본 설계 원칙

1. route 구조는 역할과 책임을 드러내야 한다.
- student용 읽기 API와 review용 변경 API를 섞지 않는다.

2. formal wiki는 직접 수정 API를 두지 않는다.
- wiki 반영은 항상 review action을 경유한다.

3. query API는 답변과 write-back 계획을 함께 반환할 수 있어야 한다.
- Knowloop는 chat completion API가 아니라 memory workflow API다.

4. actor context는 모든 비-system API에서 명시되어야 한다.
- 현재 MVP는 완전한 인증 시스템 전 단계이므로 요청 컨텍스트를 API 계약에 포함한다.

5. mutating action은 idempotent하게 재시도 가능해야 한다.
- 승인, 병합, 폐기 같은 review action은 중복 실행에 안전해야 한다.

6. API는 단순 CRUD보다 workflow를 드러내야 한다.
- `approve`, `merge`, `drop`, `patch-preview` 같은 액션형 endpoint를 허용한다.

7. role boundary를 path와 validation 양쪽에서 막는다.
- route 이름만 role별로 나누고 실제 검사에서 풀어주지 않는 구조는 피한다.

---

## 4. Base Contract

## 4.1 Base URL

MVP API base path:

```text
/api/v1
```

예외:

- 로컬 헬스체크용 `/healthz`, `/readyz`

## 4.2 Content Type

- Request: `application/json`
- Response: `application/json`

MVP에서는 multipart file upload보다
`text or metadata registration`
방식을 먼저 구현한다.

## 4.3 Time Format

모든 시간은 UTC 기준 ISO 8601 문자열을 사용한다.

예:

```text
2026-04-08T10:30:00Z
```

## 4.4 ID Format

모든 ID는 `docs/architecture/data-contracts.md`를 따른다.

예:

- `src-*`
- `ses-*`
- `cand-*`
- `page-*`
- `learn-*`

---

## 5. Request Context Headers

system endpoint를 제외한 모든 API는 아래 header contract를 따른다.

필수 header:

- `X-Knowloop-Role`
- `X-Knowloop-Actor-Id`
- `X-Knowloop-Course-Id`
- `X-Knowloop-Class-Id`

선택 header:

- `X-Knowloop-Domain`
- `X-Request-Id`
- `Idempotency-Key`

의미:

- `X-Knowloop-Role`: `student`, `instructor`, `operator`, `validator`, `system`
- `X-Knowloop-Actor-Id`: 요청 주체 식별자
- `X-Knowloop-Course-Id`: 과목 범위
- `X-Knowloop-Class-Id`: 반/운영 범위
- `X-Knowloop-Domain`: `academic`, `operations`, `review`
- `X-Request-Id`: 추적용 클라이언트 request id
- `Idempotency-Key`: 승인, 병합, 폐기, 등록 같은 mutating action의 안전한 재시도 키

MVP 주의:

- 현재 단계에서는 이 header들이 trusted development context로 들어온다고 가정한다.
- 추후 인증/인가가 도입되면, 이 값들은 auth middleware가 채우는 canonical context로 대체할 수 있다.

---

## 6. Response Envelope

## 6.1 Success Response

모든 성공 응답은 아래 envelope를 따른다.

```json
{
  "request_id": "req-20260408-001",
  "data": {},
  "meta": {}
}
```

규칙:

- `request_id`는 항상 포함
- `data`는 주 응답 payload
- `meta`는 pagination, counts, flags 같은 부가 정보

## 6.2 Error Response

모든 오류 응답은 아래 envelope를 따른다.

```json
{
  "request_id": "req-20260408-001",
  "error": {
    "code": "candidate_not_open",
    "message": "Only open candidates can be approved.",
    "details": {
      "candidate_id": "cand-faq-..."
    }
  }
}
```

## 6.3 Common Error Codes

- `invalid_request`
- `missing_context`
- `forbidden_role`
- `forbidden_scope`
- `not_found`
- `duplicate_action`
- `candidate_not_open`
- `candidate_conflict`
- `wiki_conflict`
- `insufficient_verified_context`
- `validation_failed`
- `internal_error`

---

## 7. Pagination and Filtering

MVP list endpoint는 아래 query parameter를 공통 지원한다.

- `limit`
- `offset`

선택 필터:

- `status`
- `kind`
- `domain`
- `q`
- `updated_after`

기본 규칙:

- 기본 `limit`은 20
- 최대 `limit`은 100
- 정렬 기본값은 최신순

---

## 8. Shared Response Shapes

## 8.1 RetrievalRef

```json
{
  "entity_type": "wiki_page",
  "entity_id": "page-concepts-chain-rule",
  "reason": "high_relevance",
  "source_refs": [
    {
      "source_id": "src-lecture-note-...",
      "source_type": "lecture_note"
    }
  ]
}
```

## 8.2 WritebackPlanItem

```json
{
  "kind": "candidate",
  "action": "create",
  "status": "open",
  "target_id": "cand-faq-...",
  "explanation": "Repeated deadline question detected."
}
```

## 8.3 CandidateListItem

```json
{
  "candidate_id": "cand-misconception-...",
  "kind": "misconception",
  "status": "open",
  "title": "Chain rule and product rule confusion",
  "class_id": "class-calculus-1-2026-spring-a",
  "course_id": "course-calculus-1",
  "confidence": 0.82,
  "created_at": "2026-04-08T10:30:00Z"
}
```

## 8.4 WikiPageSummary

```json
{
  "page_id": "page-concepts-chain-rule",
  "domain": "concepts",
  "title": "Chain Rule",
  "summary": "Derivative rule for compositions.",
  "updated_at": "2026-04-08T10:30:00Z"
}
```

---

## 9. Endpoint Access Matrix

| Endpoint Group | student | instructor | operator | validator | system |
|---|---|---|---|---|---|
| `GET /system/*` | R | R | R | R | R |
| `POST /query/respond` | R | R | R | R | R |
| `GET /student/*` | R-own | - | - | - | R / W |
| `GET /instructor/*` | - | R-scope | - | 제한적 R-scope | R / W |
| `GET /review/*` | - | R-scope | 제한적 operations only | R-scope | R / W |
| `POST /review/*` | - | W-approve scope | 제한적 operations only | W-approve scope | R / W |
| `GET /wiki/*` | R-scope | R-scope | operations only | R-scope | R / W |
| `POST /sources/register` | - | W-scope | W-scope | - | R / W |
| `GET /sources/*` | - | R-scope | R-scope | R-scope | R / W |
| `GET /audit/events` | - | 제한적 R-scope | 제한적 R-scope | R-scope | R / W |

설명:

- student는 review endpoint를 직접 호출하지 않는다.
- operator는 academic review action을 수행하지 않는다.
- validator는 approve / merge / drop 판단에 필요한 review, wiki, audit 범위에 접근한다.

---

## 10. System Endpoints

## 10.1 `GET /api/v1/system/health`

목적:

- 앱 프로세스가 살아 있는지 확인

응답:

```json
{
  "request_id": "req-health",
  "data": {
    "status": "ok"
  },
  "meta": {}
}
```

## 10.2 `GET /api/v1/system/ready`

목적:

- storage path, config, runtime dependency가 준비되었는지 확인

응답 data 예시:

```json
{
  "status": "ready",
  "checks": {
    "data_root": "ok",
    "manifest": "ok",
    "sessions_db": "ok",
    "audit_db": "ok"
  }
}
```

---

## 11. Source Endpoints

## 11.1 `POST /api/v1/sources/register`

목적:

- raw source를 등록하고 canonical `source_id`를 부여

허용 역할:

- `instructor`
- `operator`
- `system`

도메인 규칙:

- 대부분의 `source_type`은 academic 또는 operations 중 하나로 고정된다.
- `announcement`는 `X-Knowloop-Domain`에 따라 academic 또는 operations로 등록될 수 있다.
- `system`이 `announcement`를 등록할 때는 `X-Knowloop-Domain`을 명시해야 한다.

request body:

```json
{
  "source_type": "lecture_note",
  "title": "Week 03 Chain Rule",
  "content": "# Chain Rule\n...",
  "mime_type": "text/markdown",
  "filename": "week-03-chain-rule.md",
  "tags": [
    "week-03",
    "chain-rule"
  ]
}
```

response data:

```json
{
  "source_id": "src-lecture-note-class-calculus-1-2026-spring-a-week-03-20260408T103000Z",
  "source_type": "lecture_note",
  "domain": "academic",
  "title": "Week 03 Chain Rule",
  "status": "registered",
  "stored_path": "data/raw/lecture-note/class-calculus-1-2026-spring-a/...",
  "checksum": "sha256:...",
  "created_at": "2026-04-08T10:30:00Z"
}
```

status code:

- `201 Created`

주의:

- MVP에서는 multipart file upload보다 text registration을 우선한다.
- 실제 파일 업로드는 후속 slice에서 추가할 수 있다.

## 11.2 `GET /api/v1/sources`

목적:

- source 목록 조회

주요 query params:

- `source_type`
- `limit`
- `offset`
- `q`

응답 data:

- source summary 배열

## 11.3 `GET /api/v1/sources/{source_id}`

목적:

- 특정 source 메타데이터 조회

주의:

- raw content 전문 반환은 role과 domain에 따라 제한할 수 있다.
- validator/instructor가 필요 범위만 보도록 기본값을 메타데이터 우선으로 둔다.

---

## 12. Query Endpoint

## 12.1 `POST /api/v1/query/respond`

목적:

- Knowloop의 핵심 질문 응답 endpoint
- 답변과 retrieval 근거, write-back 계획을 함께 반환

허용 역할:

- `student`
- `instructor`
- `operator`
- `validator`
- `system`

request body:

```json
{
  "message": "체인룰이 곱의 미분이랑 뭐가 다른지 모르겠어요.",
  "attachment_source_ids": [],
  "allow_raw_source_fallback": true,
  "response_mode": "default"
}
```

request body 규칙:

- `message`는 필수
- `attachment_source_ids`는 현재 session에서 참조할 source id 목록
- `allow_raw_source_fallback`은 wiki coverage 부족 시 raw source 조회 허용 여부
- `response_mode`는 향후 `default`, `concise`, `teaching`, `review` 같은 스타일 확장용

response data:

```json
{
  "answer": "체인룰은 합성함수의 미분 규칙이고, 곱의 미분은 두 함수의 곱을 미분하는 규칙입니다.",
  "answer_basis": [
    "formal_wiki",
    "session_context",
    "learning_context"
  ],
  "retrieval_refs": [
    {
      "entity_type": "wiki_page",
      "entity_id": "page-concepts-chain-rule",
      "reason": "high_relevance"
    }
  ],
  "writeback_plan": [
    {
      "kind": "session",
      "action": "save",
      "status": "registered",
      "target_id": "ses-student-stu-kim-minji-..."
    },
    {
      "kind": "learning_note",
      "action": "update",
      "status": "planned",
      "target_id": "learn-stu-kim-minji-calculus-1-..."
    },
    {
      "kind": "candidate",
      "action": "create",
      "status": "open",
      "target_id": "cand-misconception-..."
    }
  ],
  "session_id": "ses-student-stu-kim-minji-...",
  "created_at": "2026-04-08T10:35:00Z"
}
```

status code:

- `200 OK`

에러:

- `400 invalid_request`
- `403 forbidden_role`
- `422 missing_context`
- `409 insufficient_verified_context`

중요 규칙:

- 이 endpoint는 formal wiki를 직접 수정하지 않는다.
- 최대 출력은 `writeback_plan`까지다.
- 실제 candidate 승인이나 wiki 반영은 review endpoint에서만 발생한다.

---

## 13. Student Endpoints

## 13.1 `GET /api/v1/student/sessions`

목적:

- student 자신의 최근 질문/답변 기록 조회

허용 역할:

- `student`
- `system`

query params:

- `limit`
- `offset`

response data:

```json
{
  "items": [
    {
      "session_id": "ses-student-stu-kim-minji-...",
      "question": "체인룰이 뭐예요?",
      "answer_preview": "체인룰은 합성함수...",
      "created_at": "2026-04-08T10:35:00Z"
    }
  ]
}
```

원칙:

- 항상 own scope만 반환
- 다른 학생 세션을 조회하는 일반 endpoint는 두지 않는다

## 13.2 `GET /api/v1/student/learning`

목적:

- student 개인 learning layer snapshot 조회

허용 역할:

- `student`
- `system`

response data:

```json
{
  "learning_note_id": "learn-stu-kim-minji-calculus-1-...",
  "concepts": [
    "chain rule"
  ],
  "gaps": [
    "product rule과 chain rule을 혼동함"
  ],
  "next_actions": [
    "chain rule 예제 2개 다시 풀기"
  ],
  "updated_at": "2026-04-08T10:35:00Z"
}
```

원칙:

- MVP에서는 `notes`, `gaps`, `next_actions`를 우선 제공
- `flashcards`, `review_queue`는 후속 구현

---

## 14. Instructor Endpoints

## 14.1 `GET /api/v1/instructor/insights`

목적:

- 교강사 대시보드용 집계 신호 제공

허용 역할:

- `instructor`
- `validator`
- `system`

query params:

- `kind`
- `limit`
- `updated_after`

response data:

```json
{
  "candidate_summary": {
    "open": 8,
    "misconception": 3,
    "faq": 4,
    "intervention": 1
  },
  "repeated_questions": [
    {
      "title": "과제 마감 질문 반복",
      "count": 5
    }
  ],
  "misconception_hotspots": [
    {
      "title": "chain rule/product rule confusion",
      "count": 3
    }
  ],
  "recommended_interventions": [
    "다음 수업 시작 전 chain rule과 product rule 비교 설명 추가"
  ]
}
```

원칙:

- 원문 session transcript 전체 대신 집계 결과를 우선 제공
- 개인 student 기록 직접 노출은 기본 contract에 포함하지 않는다

---

## 15. Review Endpoints

review endpoint는 Knowloop의 핵심 품질 게이트다.

## 15.1 `GET /api/v1/review/candidates`

목적:

- candidate review inbox 목록 조회

허용 역할:

- `instructor`
- `validator`
- `system`
- `operator` for operations domain only

query params:

- `status`
- `kind`
- `domain`
- `limit`
- `offset`

response data:

```json
{
  "items": [
    {
      "candidate_id": "cand-faq-...",
      "kind": "faq",
      "status": "open",
      "title": "Homework submission deadline",
      "confidence": 0.91,
      "created_at": "2026-04-08T10:30:00Z"
    }
  ]
}
```

## 15.2 `GET /api/v1/review/candidates/{candidate_id}`

목적:

- candidate 상세, source refs, session refs, related wiki page 조회

response data 예시:

```json
{
  "candidate": {
    "candidate_id": "cand-faq-...",
    "kind": "faq",
    "status": "open",
    "title": "Homework submission deadline",
    "summary": "Repeated student questions about submission time.",
    "source_refs": [
      {
        "source_id": "src-announcement-...",
        "source_type": "announcement"
      }
    ],
    "session_refs": [
      "ses-student-..."
    ]
  },
  "related_wiki_pages": [
    {
      "page_id": "page-faq-homework-submission",
      "title": "Homework Submission"
    }
  ]
}
```

## 15.3 `POST /api/v1/review/candidates/{candidate_id}/patch-preview`

목적:

- candidate를 wiki에 반영할 경우의 patch draft 미리보기 생성

request body:

```json
{
  "target_page_id": "page-faq-homework-submission",
  "target_path": "data/wiki/faq/homework-submission.md",
  "notes": "기존 FAQ에 제출 시간 항목 추가"
}
```

response data:

```json
{
  "patch": {
    "operation": "update",
    "target_page_id": "page-faq-homework-submission",
    "summary": "Add submission deadline clarification.",
    "change_plan": [
      "FAQ 항목 추가",
      "source refs 보강"
    ]
  }
}
```

원칙:

- preview는 wiki를 실제 수정하지 않는다.
- instructor/validator가 diff를 먼저 확인할 수 있어야 한다.

## 15.4 `POST /api/v1/review/candidates/{candidate_id}/approve`

목적:

- open candidate를 promoted로 전이하고 wiki 반영을 트리거

필수 header:

- `Idempotency-Key`

request body:

```json
{
  "target_page_id": "page-faq-homework-submission",
  "target_path": "data/wiki/faq/homework-submission.md",
  "approval_notes": "과목 공통 FAQ로 승격"
}
```

response data:

```json
{
  "candidate_id": "cand-faq-...",
  "from_status": "open",
  "to_status": "promoted",
  "approved_at": "2026-04-08T11:00:00Z",
  "wiki_update": {
    "page_id": "page-faq-homework-submission",
    "updated_at": "2026-04-08T11:00:00Z"
  },
  "audit_event_id": "evt-candidate-promoted-..."
}
```

status code:

- `200 OK`
- `409 candidate_not_open`
- `409 wiki_conflict`

원칙:

- 사람 승인 없는 promote는 불가
- `open` 상태가 아니면 승인할 수 없다
- approve는 candidate status 변경과 wiki 반영, audit 기록을 함께 다룬다

## 15.5 `POST /api/v1/review/candidates/{candidate_id}/merge`

목적:

- 중복 또는 유사 candidate를 기존 candidate에 병합

필수 header:

- `Idempotency-Key`

request body:

```json
{
  "target_candidate_id": "cand-faq-existing-...",
  "merge_notes": "동일 FAQ 패턴으로 통합"
}
```

response data:

```json
{
  "candidate_id": "cand-faq-...",
  "from_status": "open",
  "to_status": "merged",
  "merged_into": "cand-faq-existing-...",
  "audit_event_id": "evt-candidate-merged-..."
}
```

## 15.6 `POST /api/v1/review/candidates/{candidate_id}/drop`

목적:

- 지식 가치가 없거나 근거가 부족한 candidate 폐기

필수 header:

- `Idempotency-Key`

request body:

```json
{
  "reason": "insufficient_shared_value",
  "drop_notes": "개인 일정 질문으로 course-wide FAQ 가치가 없음"
}
```

response data:

```json
{
  "candidate_id": "cand-faq-...",
  "from_status": "open",
  "to_status": "dropped",
  "audit_event_id": "evt-candidate-dropped-..."
}
```

원칙:

- drop은 delete가 아니다
- 원본 source와 session trace는 보존한다

---

## 16. Wiki Endpoints

## 16.1 `GET /api/v1/wiki/pages`

목적:

- course wiki explorer용 목록 조회

허용 역할:

- `student`
- `instructor`
- `validator`
- `system`
- `operator` for operations domain only

query params:

- `domain`
- `q`
- `limit`
- `offset`

response data:

```json
{
  "items": [
    {
      "page_id": "page-concepts-chain-rule",
      "domain": "concepts",
      "title": "Chain Rule",
      "summary": "Derivative rule for compositions.",
      "updated_at": "2026-04-08T11:00:00Z"
    }
  ]
}
```

## 16.2 `GET /api/v1/wiki/pages/{page_id}`

목적:

- 특정 wiki page 조회

response data:

```json
{
  "page_id": "page-concepts-chain-rule",
  "domain": "concepts",
  "title": "Chain Rule",
  "summary": "Derivative rule for compositions.",
  "body_markdown": "# Chain Rule\n...",
  "source_refs": [
    {
      "source_id": "src-lecture-note-...",
      "source_type": "lecture_note"
    }
  ],
  "candidate_refs": [
    "cand-misconception-..."
  ],
  "updated_at": "2026-04-08T11:00:00Z"
}
```

중요:

- `POST /wiki/pages` 또는 `PUT /wiki/pages/{page_id}` 같은 직접 쓰기 endpoint는 제공하지 않는다.
- wiki 수정은 review 승인 흐름을 따른다.

---

## 17. Audit Endpoints

## 17.1 `GET /api/v1/audit/events`

목적:

- review와 승격 이력 추적

허용 역할:

- `validator`
- `instructor` limited scope
- `operator` limited operations scope
- `system`

query params:

- `entity_type`
- `entity_id`
- `action`
- `limit`
- `offset`

response data:

```json
{
  "items": [
    {
      "event_id": "evt-candidate-promoted-...",
      "entity_type": "candidate",
      "entity_id": "cand-faq-...",
      "action": "candidate_promoted",
      "actor_role": "instructor",
      "actor_id": "ins-calculus-team",
      "created_at": "2026-04-08T11:00:00Z"
    }
  ]
}
```

---

## 18. Intentionally Missing Endpoints

MVP에서 일부 endpoint는 의도적으로 만들지 않는다.

1. `POST /api/v1/wiki/pages`
- 직접 wiki 생성/수정 금지

2. `GET /api/v1/student/candidates`
- student에게 review 전 candidate 노출 금지

3. `GET /api/v1/sessions/all`
- broad transcript dump 금지

4. `POST /api/v1/review/auto-promote`
- 사람 승인 없는 자동 승격 금지

5. `GET /api/v1/learning/{other-student-id}`
- 타 학생 개인 learning layer 조회 금지

이 endpoint들이 없는 이유는
Knowloop가 단순 CRUD app이 아니라
권한과 품질 게이트가 중심인 workflow app이기 때문이다.

---

## 19. HTTP Status Policy

대표 status code 사용 규칙:

- `200 OK`: 일반 성공
- `201 Created`: source 등록 성공
- `400 Bad Request`: body/param 형식 오류
- `403 Forbidden`: role 또는 scope 불일치
- `404 Not Found`: 없는 entity
- `409 Conflict`: 상태 전이 불가, wiki 충돌, 중복 action
- `422 Unprocessable Entity`: 계약상 필수 맥락 부족
- `500 Internal Server Error`: 비예상 내부 오류

---

## 20. Implementation Order

API 구현 우선순위는 아래가 적절하다.

1. `GET /api/v1/system/health`
2. `GET /api/v1/system/ready`
3. `POST /api/v1/query/respond`
4. `GET /api/v1/wiki/pages`
5. `GET /api/v1/wiki/pages/{page_id}`
6. `GET /api/v1/student/sessions`
7. `GET /api/v1/student/learning`
8. `GET /api/v1/review/candidates`
9. `GET /api/v1/review/candidates/{candidate_id}`
10. `POST /api/v1/review/candidates/{candidate_id}/patch-preview`
11. `POST /api/v1/review/candidates/{candidate_id}/approve`
12. `POST /api/v1/review/candidates/{candidate_id}/merge`
13. `POST /api/v1/review/candidates/{candidate_id}/drop`
14. `GET /api/v1/instructor/insights`
15. `POST /api/v1/sources/register`
16. `GET /api/v1/audit/events`

이 순서의 의도:

- 먼저 demo 핵심인 `질문 -> 조회 -> candidate review -> wiki 반영`
를 닫고,
- 그 다음 ingest와 audit 조회를 보강한다.

---

## 21. 다음 연결 문서

이 문서 다음에 가장 자연스럽게 이어지는 문서는 아래 2개다.

1. `docs/product/ui-information-architecture.md`
- 어떤 화면이 어떤 endpoint를 호출하는지 정의

2. `docs/product/fixture-catalog.md`
- 위 endpoint들을 검증할 fixture 세트를 정의

---

## 22. 한 줄 결론

Knowloop MVP API 계약은
`query는 답변과 write-back 계획을 반환하고, review endpoint만 candidate lifecycle과 wiki 반영을 변경하며, role별 읽기 범위는 path와 validation 양쪽에서 강제한다`
를 핵심 원칙으로 한다.

## 18. Source Registration Note

- `announcement` registrations may produce `source_id` values such as `src-announcement-acad-...` or `src-announcement-ops-...`.
- The `stored_path` for those records is segmented by domain: `data/raw/announcement/<domain>/<class-id>/...`.
- `source_id` values keep a short readable title prefix plus a short hash suffix so registrations remain stable for non-ASCII and long-prefix titles.
- `POST /api/v1/sources/register` requires `Idempotency-Key` so retries can safely recover the same raw source.
- When storage is temporarily locked by another writer, the endpoint returns `503` with `error.code = "storage_busy"`.
