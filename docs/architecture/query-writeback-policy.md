# Knowloop Query / Write-back Policy

## 1. 문서 목적

이 문서는 Knowloop MVP에서
`질문 시 어떤 순서로 지식을 조회할지`와
`답변 후 무엇을 어떤 조건으로 다시 축적할지`를 고정하는 정책 문서다.

이 문서는 특히 아래 4개 문서의 사이를 메운다.

- `docs/product/mvp-scope.md`
- `docs/architecture/data-contracts.md`
- `docs/architecture/promotion-policy.md`
- `docs/product/role-permissions.md`

즉, 이 문서는
`query path의 우선순위`,
`answer generation의 근거 규칙`,
`write-back의 허용 범위`,
`절대 하면 안 되는 자동 반영`
을 명시한다.

---

## 2. 기본 원칙

1. Knowloop의 기본 답변 지식원은 `formal wiki`다.
- 단순 raw chunk 검색 결과보다 검토된 wiki를 우선한다.

2. `session memory`는 맥락 기억이지, 공식 지식원이 아니다.
- 최근 대화 흐름을 잇기 위해 사용한다.
- 공식 사실 판단은 wiki 또는 명시된 source에 기대야 한다.

3. `candidate`는 검토 대기 지식이다.
- query 시 참고는 가능하지만, `open` candidate를 공식 사실처럼 단정해서 답변하지 않는다.

4. `learning layer`는 학생 개인 학습 보조 자산이다.
- 개인화와 복습 추천에는 사용한다.
- 공용 사실 지식처럼 취급하지 않는다.

5. `raw source`는 MVP에서 기본 답변층이 아니라 fallback 검증층이다.
- wiki coverage가 부족하거나, 사용자가 방금 업로드한 자료를 직접 묻는 경우에만 우선 사용한다.

6. query와 write-back은 연결되지만 같은 것이 아니다.
- 답변은 먼저 생성한다.
- 그 다음 답변과 질문을 바탕으로 write-back 후보를 만든다.

7. query 경로는 `formal wiki`를 직접 수정하지 않는다.
- query에서 가능한 최대 출력은 `candidate 생성` 또는 `wiki patch draft의 입력 정보 생성`까지다.
- formal wiki 반영은 별도 승인 흐름을 따른다.

---

## 3. Query Scope Resolution

모든 query는 답변 전에 아래 범위를 먼저 고정한다.

1. `actor_role`
2. `user_id`
3. `course_id`
4. `class_id`
5. `domain`

기본 domain 규칙:

- `student`, `instructor`의 기본 domain은 `academic`
- `operator`의 기본 domain은 `operations`
- `validator`의 기본 domain은 `review`

범위가 잠기지 않으면 query를 계속 진행하지 않는다.

MVP 원칙:

- role 미확정 상태로 broad retrieval 하지 않는다.
- class 범위가 필요한 질문은 `class_id`를 우선한다.
- 공용 과목 지식은 `course_id` 기준으로 본다.

---

## 4. Query Retrieval Priority

## 4.1 공통 조회 순서

기본 query 순서는 아래와 같다.

1. 역할과 범위 해석
2. 최근 `session memory` 회수
3. 관련 `formal wiki` 검색
4. 역할별 보조 레이어 조회
5. 필요한 경우에만 `raw source` fallback
6. 답변 생성
7. write-back 계획 생성

이 순서의 핵심은
`대화 맥락은 session에서`,
`사실 지식은 wiki에서`,
`개인화는 learning에서`,
`미검증 힌트는 candidate에서`
가져오는 것이다.

## 4.2 Session Memory Retrieval

session retrieval 목적:

- 직전 질문과 답변 맥락 유지
- 같은 학생의 반복 질문 여부 파악
- 직전 답변과 이번 답변의 연결성 확보

MVP 기본 규칙:

- 최근 3~5건의 동일 `user_id + class_id` 범위 session을 우선 조회한다.
- 너무 오래된 session은 기본 query에서 제외한다.
- class가 다른 session은 기본적으로 섞지 않는다.

session memory는 아래 용도로만 쓴다.

- 대명사 해석
- 바로 직전 질문 이어받기
- 반복 질문 여부 탐지
- write-back 후보 생성

session memory만으로 새로운 공식 사실을 단정하지 않는다.

## 4.3 Formal Wiki Retrieval

formal wiki는 기본 답변층이다.

MVP 기본 규칙:

- `course_id` 또는 `domain`에 맞는 wiki page를 우선 검색한다.
- 관련도 높은 3~5개 page를 상한으로 둔다.
- wiki page의 `source_refs`와 `candidate_refs`는 내부 추적용으로 함께 회수할 수 있다.

formal wiki가 충분히 관련 있으면:

- raw source 추가 조회 없이 wiki 중심으로 답변한다.

formal wiki가 부분적으로만 관련 있으면:

- session memory와 learning layer를 보조로 쓴다.

## 4.4 Learning Layer Retrieval

learning layer는 학생 역할에서만 적극 사용한다.

사용 목적:

- 이미 어려워한 개념 재인식
- 복습 우선순위 반영
- next actions 제안

MVP 규칙:

- `student` query에서만 `student_id + course_id` 범위를 조회한다.
- `instructor`는 개별 학생 learning layer 원문을 기본 query에서 조회하지 않는다.
- `operator`는 learning layer를 조회하지 않는다.

learning layer는 답변의 톤과 설명 깊이를 조정하는 데 쓰되,
공식 지식의 근거로 인용하지 않는다.

## 4.5 Candidate Retrieval

candidate는 role에 따라 읽는 방식이 달라진다.

`student` query:

- `open` candidate를 공식 사실처럼 직접 인용하지 않는다.
- 필요하면 내부적으로만 `이 학생이 자주 헷갈리는 주제` 정도의 힌트로 쓴다.

`instructor` query:

- 반복 질문, misconception, intervention candidate 집계를 적극 조회한다.
- 이 경우 candidate는 수업 개입과 FAQ 검토를 위한 운영 힌트다.

`operator` query:

- operations domain의 candidate만 조회한다.

`validator` query:

- candidate 상세와 source trace를 우선 조회한다.

## 4.6 Raw Source Fallback

raw source는 아래 경우에만 query에서 적극 조회한다.

1. 사용자가 방금 올린 첨부자료 자체를 묻는 경우
2. formal wiki coverage가 부족한 경우
3. wiki와 candidate 사이에 충돌이 있어 검증이 필요한 경우

raw source를 사용한 답변 원칙:

- 답변에서 `공식 wiki 반영 전 자료 기준`임을 분명히 한다.
- 그 결과를 곧바로 formal wiki 사실로 취급하지 않는다.
- 필요하면 `unresolved_question` 또는 적절한 candidate를 남긴다.

---

## 5. Role-Specific Query Policy

## 5.1 Student

조회 우선순위:

1. course/class 범위 formal wiki
2. 본인 최근 session memory
3. 본인 learning layer
4. 필요 시 raw source fallback

답변 원칙:

- 다른 학생의 데이터는 절대 사용하지 않는다.
- 위키 근거가 충분하면 명확히 설명한다.
- 위키 근거가 약하면 불확실성을 드러내고 보수적으로 답변한다.
- 답변 끝에는 가능하면 `다음 복습 행동`을 제안한다.

## 5.2 Instructor

조회 우선순위:

1. course/class 범위 formal wiki
2. 반 단위 aggregated session 패턴
3. candidate 집계
4. 필요 시 강의자료 raw source

답변 원칙:

- 개별 학생 원문 session 전체를 기본값으로 드러내지 않는다.
- 수업 개입, 반복 오개념, FAQ 초안 관점으로 답변한다.
- 개인 상담 수준의 민감 내용은 기본 query 범위에서 제외한다.

## 5.3 Operator

조회 우선순위:

1. operations wiki
2. operator session memory
3. operations candidate
4. 관련 공지/규정 raw source

답변 원칙:

- 학습 영역과 운영 영역을 섞지 않는다.
- academic misconception candidate를 운영 답변에 사용하지 않는다.

## 5.4 Validator

조회 우선순위:

1. candidate 상세
2. source_refs / session_refs
3. target wiki page
4. audit event

답변 원칙:

- validator query는 사실 답변보다 `승격 판단 보조`에 가깝다.
- promote / merge / drop 판단 근거를 먼저 제시한다.

---

## 6. Answer Generation Contract

답변 생성 시 시스템은 최소한 아래 정보를 내부적으로 가져야 한다.

- `role`
- `course_id`
- `class_id`
- `retrieval_refs`
- `answer_basis`

`answer_basis`는 아래 중 하나 또는 조합이다.

- `formal_wiki`
- `formal_wiki + session_context`
- `formal_wiki + learning_context`
- `raw_source_fallback`
- `insufficient_verified_context`

답변 생성 규칙:

1. 검증된 wiki가 있으면 wiki를 우선 사용한다.
2. session memory는 설명 연결과 반복 질문 파악에만 쓴다.
3. learning layer는 학생 개인화에만 쓴다.
4. open candidate는 사실 근거가 아니라 운영 힌트로만 쓴다.
5. 충분한 근거가 없으면 억지로 단정하지 않는다.

좋은 답변의 형태:

- 질문에 대한 직접 답변
- 필요한 경우 간단한 근거 또는 참조 층 설명
- 학생이라면 next action 또는 review hint
- 교강사라면 candidate / intervention 시사점

---

## 7. Write-back Policy

## 7.1 항상 저장되는 것

모든 정상 query 후에는 최소한 아래가 저장된다.

- `SessionRecord`
- `retrieval_refs`
- `created_at`

즉, Knowloop는 답변만 하고 끝나지 않는다.
정상 응답이 있었다면 그 질문-답변 상호작용은 session memory에 남는다.

## 7.2 Student Query Write-back

학생 query 후에는 아래 두 종류의 write-back을 평가한다.

1. `LearningNote` 업데이트 후보
2. `CandidateItem` 생성 후보

### LearningNote를 갱신하는 경우

아래 중 하나 이상이면 learning update 후보를 만든다.

- 설명된 핵심 개념이 분명하다
- 학생의 오해 또는 gap이 드러났다
- 다음 복습 행동을 제안할 수 있다
- 기존 learning layer와 연결 가능한 개념이 있다

MVP 기준 learning write-back은 우선 아래 범위에 집중한다.

- `notes`
- `gaps`
- `next_actions`

`flashcards`, `review_queue`는 후순위다.

### Candidate를 생성하는 경우

아래 중 하나 이상이면 candidate 생성 후보를 만든다.

- 동일하거나 매우 유사한 질문이 반복된다
- 명확한 misconception pattern이 보인다
- 공식 wiki에 아직 없는 FAQ 가치가 있다
- unresolved question으로 남겨야 한다
- 교강사 intervention이 필요해 보인다

query 경로에서 생성된 candidate 기본 상태:

- `status = open`

## 7.3 Instructor Query Write-back

교강사 query 후에는 아래 write-back이 가능하다.

- candidate 생성 또는 기존 candidate 보강
- intervention draft 생성
- wiki patch draft 입력 정보 생성

하지만 교강사와의 일반 대화가 자동으로 formal wiki를 수정하지는 않는다.

formal wiki 반영은 아래가 모두 필요하다.

- candidate 또는 patch draft 존재
- source traceability
- 승인 행위
- audit event 기록

## 7.4 Operator Query Write-back

운영 query 후에는 아래만 허용한다.

- operations candidate 생성
- operations FAQ draft 생성
- operations wiki patch draft 입력 정보 생성

학습용 candidate나 학생 learning layer는 갱신하지 않는다.

## 7.5 Validator Query Write-back

validator는 보통 end-user query보다 review action을 수행한다.

이때 가능한 write-back:

- `candidate_promoted`
- `candidate_merged`
- `candidate_dropped`
- `wiki_updated`
- 관련 audit event

단, 이 write-back은 일반 답변 경로가 아니라
검토 액션 경로에서만 허용한다.

---

## 8. Write-back 금지 또는 축소 조건

아래 경우에는 session 저장 외의 write-back을 제한하거나 금지한다.

1. 인사말, 잡담, 테스트 입력처럼 지식 가치가 거의 없는 경우
2. 근거가 부족해 신뢰 가능한 구조화를 할 수 없는 경우
3. 중복 질문으로 learning/candidate에 같은 내용이 방금 반영된 경우
4. 답변이 거절되었거나 안전 정책에 의해 제한된 경우
5. role 또는 scope가 불명확한 경우

중복 최소화 규칙:

- session은 남기되,
- near-duplicate learning update와 candidate 생성은 줄인다.

---

## 9. Source Traceability and Audit

query 이후 생성되는 모든 주요 write-back 후보는
가능하면 아래 연결 정보를 가진다.

- `source_refs`
- `session_refs`
- `course_id`
- `class_id`
- `actor_role`

기본 audit event 예시:

- `session_saved`
- `learning_generated`
- `candidate_created`
- `candidate_promoted`
- `candidate_merged`
- `candidate_dropped`
- `wiki_updated`

원칙:

- source traceability 없는 formal wiki 반영은 금지
- 사람이 나중에 추적할 수 없는 write-back은 지양

---

## 10. Failure Handling

## 10.1 Wiki coverage가 부족한 경우

처리 원칙:

- 가능한 범위에서 raw source fallback으로 답변
- 답변에서 현재 근거 수준을 드러냄
- session은 저장
- 필요하면 `unresolved_question` candidate 생성

## 10.2 Write-back 일부 실패

처리 원칙:

- 답변 생성이 성공했다면 session 저장을 최우선으로 시도한다.
- learning update 또는 candidate 생성이 실패하면 audit에 남긴다.
- 부가 write-back 실패 때문에 사용자 답변 전체를 버리지 않는다.

## 10.3 근거 충돌

formal wiki와 raw source 또는 candidate가 충돌하면:

- wiki를 무시하고 임의로 덮어쓰지 않는다.
- 충돌 사실을 review 대상으로 남긴다.
- 필요하면 validator/instructor 검토 경로로 보낸다.

---

## 11. MVP 구현 우선순위

이 문서를 기준으로 MVP에서 먼저 구현할 것은 아래 순서가 적절하다.

1. query scope resolution
2. formal wiki + session memory retrieval
3. student learning write-back
4. candidate generation write-back
5. instructor review-triggered patch draft
6. audit event 저장

후순위:

- raw source 고도화 retrieval
- flashcards / review queue write-back
- 고급 reranking
- 복합 multi-turn thread memory

---

## 12. 다음 문서와의 연결

이 문서 다음에 바로 이어서 구체화할 문서는 아래 2개다.

1. `docs/architecture/api-contracts.md`
- query, review, approve, merge, drop API를 어떻게 노출할지 정의

2. `docs/product/ui-information-architecture.md`
- student, instructor, review 화면이 어떤 query/write-back 액션을 호출할지 정의

참고:
- `api-contracts.md`가 작성된 이후에는 이 문서와 함께 route 설계의 상위 기준으로 사용한다.

---

## 13. 최종 결론

Knowloop MVP의 query / write-back 정책은
`formal wiki를 기본 지식원으로 삼고, session과 learning으로 맥락과 개인화를 보완하며, 답변 결과를 session / candidate / learning에 다시 축적하되, formal wiki 직접 수정은 승인 경로로만 허용한다`
로 요약된다.
