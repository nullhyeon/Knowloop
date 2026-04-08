# Knowloop Fixture Catalog

## 1. 문서 목적

이 문서는 Knowloop MVP에서 사용하는 fixture 데이터의 범위, 구조, 파일 배치, 검증 목적을 고정하는 문서다.

이 문서의 목적은 다음과 같다.

- 백엔드 구현 전에 테스트 데이터 계약을 잠근다
- 데모, API 테스트, 저장소 테스트가 같은 fixture 세트를 공유하게 만든다
- synthetic / anonymized 데이터만 사용하도록 기준을 고정한다
- 어떤 fixture가 어떤 시나리오와 어떤 endpoint를 검증하는지 추적 가능하게 만든다

이 문서는 단순 예시 문서가 아니라
MVP 테스트 데이터 운영 문서다.

---

## 2. 기본 원칙

1. fixture는 모두 repository-safe 데이터여야 한다.
- 실제 학생 이름, 실제 강의자료, 실제 상담기록을 커밋하지 않는다.

2. fixture는 synthetic 또는 충분히 anonymized된 데이터만 사용한다.
- 공개 저장소에 올라가도 개인정보 또는 기관 비밀이 드러나지 않아야 한다.

3. fixture는 문서와 API 계약을 검증하는 최소 단위여야 한다.
- 예쁘게 많은 데이터를 넣는 것보다 시나리오를 닫는 데이터가 우선이다.

4. fixture는 결정적이어야 한다.
- 같은 입력으로 같은 테스트 결과를 반복 재현할 수 있어야 한다.

5. fixture는 Knowloop의 핵심 흐름을 보여줘야 한다.
- `질문 -> session 저장 -> candidate 생성 -> 승인 -> wiki 반영 -> 다음 답변 반영`

6. fixture는 레이어 분리를 드러내야 한다.
- raw, sessions, candidate, wiki, learning, review, audit를 섞어서 하나의 덩어리로 두지 않는다.

7. fixture는 역할 경계를 검증할 수 있어야 한다.
- student, instructor, operator, validator가 서로 다른 범위를 보도록 만들어야 한다.

---

## 3. Fixture의 역할

Knowloop에서 fixture는 아래 4가지 역할을 가진다.

1. API contract test
- request/response shape가 문서와 일치하는지 확인

2. storage bootstrap test
- `sessions.db`, `audit.db`, 파일 레이어가 기대한 구조로 채워지는지 확인

3. workflow integration test
- candidate lifecycle과 wiki 반영 흐름이 닫히는지 확인

4. demo seed
- 발표 시 실제 동작처럼 보이도록 안전한 예시 데이터를 제공

즉, fixture는 테스트 보조물이 아니라
MVP 실행 계약의 일부다.

---

## 4. Canonical MVP Fixture Pack

MVP는 하나의 대표 과목/반을 중심으로 fixture를 고정한다.

## 4.1 과목과 반

- `course_id`: `course-calculus-1`
- `class_id`: `class-calculus-1-2026-spring-a`
- 기본 domain: `academic`

이 선택 이유:

- 미적분은 `개념 질문`, `오개념`, `FAQ`, `보충설명` 시나리오를 만들기 쉽다
- chain rule / product rule 혼동은 misconception fixture로 설명력이 높다

## 4.2 역할별 canonical actor

- `student`: `stu-kim-minji`
- `student`: `stu-park-jiyoon`
- `student`: `stu-lee-doyun`
- `instructor`: `ins-calculus-team`
- `operator`: `ops-academic-office`
- `validator`: `val-course-admin`

MVP 핵심 흐름은 위 6개 actor로 충분하다.

## 4.3 핵심 질문 테마

MVP에서 반드시 닫아야 하는 질문 테마는 아래 4개다.

1. chain rule과 product rule 혼동
2. 과제 제출 마감 FAQ
3. 아직 wiki에 없는 unresolved question
4. 운영 공지와 문의의 operations 분리

---

## 5. Fixture 저장 위치

실제 fixture 파일은 아래 디렉터리에 둔다.

```text
data/fixtures/
  sources/
  queries/
  sessions/
  candidates/
  reviews/
  wiki/
```

의미:

- `sources/`: raw source 등록용 fixture
- `queries/`: query request input fixture
- `sessions/`: 예상 또는 seed session record fixture
- `candidates/`: review inbox seed candidate fixture
- `reviews/`: approve / merge / drop request fixture
- `wiki/`: wiki seed와 expected wiki snapshot fixture

운영 원칙:

- fixture 내용은 `data/`의 실제 런타임 데이터와 분리한다
- 테스트가 fixture를 읽어 런타임 경로에 복제하거나 seed하는 방식으로 사용한다

---

## 6. Fixture Naming Policy

fixture 파일명은 아래 원칙을 따른다.

1. 사람이 읽을 수 있어야 한다
2. 어떤 endpoint나 시나리오를 위한 fixture인지 바로 드러나야 한다
3. 하나의 파일은 하나의 책임을 가지는 것이 좋다

예:

- `sources/lecture-note-week-03-chain-rule.md`
- `queries/student-chain-rule-confusion.json`
- `queries/student-homework-deadline-repeat.json`
- `candidates/open-misconception-chain-rule.json`
- `reviews/approve-homework-faq.json`
- `wiki/faq-homework-submission.after.md`

---

## 7. Fixture Set 구성

## 7.1 Source Fixture Set

목적:

- raw source 등록
- source traceability 검증
- wiki와 답변의 근거층 제공

필수 fixture:

| fixture id | 파일 | source_type | 목적 |
|---|---|---|---|
| `srcf-lecture-week03` | `sources/lecture-note-week-03-chain-rule.md` | `lecture_note` | chain rule 공식 지식 근거 |
| `srcf-announcement-homework` | `sources/announcement-homework-deadline.md` | `announcement` | 마감 FAQ 근거 |
| `srcf-instructor-intervention` | `sources/instructor-note-chain-rule-support.md` | `operations_note` 또는 `lecture_note` 성격의 보조 자료 | intervention 근거 |
| `srcf-ops-policy` | `sources/operations-refund-policy.md` | `operations_note` | operations domain 분리 검증 |

설명:

- `lecture_note`와 `announcement`는 MVP 핵심 시나리오에 직접 필요하다
- operations fixture는 권한 분리와 domain 분리를 확인하기 위한 최소 범위다

## 7.2 Query Fixture Set

목적:

- `POST /api/v1/query/respond` 검증
- query -> session -> write-back 계획 생성 검증

필수 fixture:

| fixture id | 파일 | actor | 기대 효과 |
|---|---|---|---|
| `qf-student-chain-rule-01` | `queries/student-chain-rule-confusion.json` | `stu-kim-minji` | learning + misconception candidate 생성 |
| `qf-student-homework-01` | `queries/student-homework-deadline-01.json` | `stu-park-jiyoon` | FAQ 패턴 1회 |
| `qf-student-homework-02` | `queries/student-homework-deadline-02.json` | `stu-lee-doyun` | FAQ 패턴 반복 누적 |
| `qf-student-unresolved-01` | `queries/student-unresolved-question.json` | `stu-kim-minji` | unresolved_question candidate 생성 |
| `qf-operator-policy-01` | `queries/operator-refund-policy.json` | `ops-academic-office` | operations domain query 검증 |

## 7.3 Session Fixture Set

목적:

- session 저장 구조 검증
- 최근 맥락 retrieval 검증
- repeated question 집계 검증

필수 fixture:

| fixture id | 파일 | 설명 |
|---|---|---|
| `sef-student-history-minji` | `sessions/student-minji-history.json` | Minji의 최근 chain rule 관련 과거 질문 묶음 |
| `sef-student-history-jiyoon` | `sessions/student-jiyoon-history.json` | 과제 제출 문의 이력 |
| `sef-student-history-doyun` | `sessions/student-doyun-history.json` | 동일 FAQ 반복 패턴 |

원칙:

- session fixture는 실제 raw transcript dump처럼 길게 만들지 않는다
- API 테스트에 필요한 최소 필드와 반복 패턴만 담는다

## 7.4 Candidate Fixture Set

목적:

- review inbox 조회
- approve / merge / drop 액션 검증

필수 fixture:

| fixture id | 파일 | kind | 상태 | 목적 |
|---|---|---|---|---|
| `caf-open-misconception-chain-rule` | `candidates/open-misconception-chain-rule.json` | `misconception` | `open` | approve 또는 merge 검증 |
| `caf-open-faq-homework` | `candidates/open-faq-homework-deadline.json` | `faq` | `open` | FAQ 승격 검증 |
| `caf-open-unresolved-integral` | `candidates/open-unresolved-integral.json` | `unresolved_question` | `open` | open 유지 검증 |
| `caf-open-operations-refund` | `candidates/open-operations-refund.json` | `operations_note` | `open` | operations review 검증 |
| `caf-dup-misconception-chain-rule` | `candidates/open-misconception-chain-rule-duplicate.json` | `misconception` | `open` | merge 검증 |

## 7.5 Review Action Fixture Set

목적:

- review endpoint body 검증
- approve / merge / drop의 idempotent 흐름 검증

필수 fixture:

| fixture id | 파일 | endpoint | 목적 |
|---|---|---|---|
| `rvf-approve-homework-faq` | `reviews/approve-homework-faq.json` | `POST /review/candidates/{id}/approve` | FAQ 승격 |
| `rvf-merge-chain-rule-dup` | `reviews/merge-chain-rule-duplicate.json` | `POST /review/candidates/{id}/merge` | duplicate candidate 병합 |
| `rvf-drop-low-value` | `reviews/drop-low-value-candidate.json` | `POST /review/candidates/{id}/drop` | 공용 가치 없는 candidate 폐기 |
| `rvf-preview-homework-faq` | `reviews/patch-preview-homework-faq.json` | `POST /review/candidates/{id}/patch-preview` | wiki patch draft 확인 |

## 7.6 Wiki Fixture Set

목적:

- seed wiki와 반영 후 expected wiki 비교
- `GET /wiki/pages` / `GET /wiki/pages/{page_id}` 검증

필수 fixture:

| fixture id | 파일 | 목적 |
|---|---|---|
| `wkf-concepts-chain-rule-seed` | `wiki/concepts-chain-rule.seed.md` | query 기본 지식층 |
| `wkf-faq-homework-seed` | `wiki/faq-homework-submission.seed.md` | 승격 전 seed page |
| `wkf-faq-homework-after` | `wiki/faq-homework-submission.after.md` | approve 후 기대 상태 |
| `wkf-misconception-chain-rule-after` | `wiki/misconception-chain-rule.after.md` | misconception 반영 기대 상태 |

---

## 8. 필수 시나리오와 Fixture 매핑

| 시나리오 | 필요한 fixture |
|---|---|
| 학생 질문 -> session 저장 | source + query + session |
| 학생 질문 -> learning layer 갱신 | source + query + learning expectation |
| 반복 질문 -> FAQ candidate 집계 | query + session + candidate |
| 교강사 승인 -> wiki 반영 | candidate + review + wiki |
| merge action | candidate duplicate + review |
| drop action | candidate + review |
| operations 분리 | operations source + operations query + operations candidate |

설명:

- 하나의 fixture가 여러 시나리오에 재사용되어도 된다
- 하지만 한 시나리오를 위해 너무 많은 fixture를 묶는 것은 피한다

---

## 9. Endpoint Coverage Map

| endpoint | 필요한 fixture 세트 |
|---|---|
| `POST /api/v1/sources/register` | source |
| `POST /api/v1/query/respond` | source + query + session |
| `GET /api/v1/student/sessions` | session |
| `GET /api/v1/student/learning` | query 결과 기반 learning expectation |
| `GET /api/v1/instructor/insights` | session + candidate |
| `GET /api/v1/review/candidates` | candidate |
| `GET /api/v1/review/candidates/{candidate_id}` | candidate + source + session |
| `POST /api/v1/review/candidates/{candidate_id}/patch-preview` | candidate + wiki + review |
| `POST /api/v1/review/candidates/{candidate_id}/approve` | candidate + wiki + review |
| `POST /api/v1/review/candidates/{candidate_id}/merge` | candidate + review |
| `POST /api/v1/review/candidates/{candidate_id}/drop` | candidate + review |
| `GET /api/v1/wiki/pages` | wiki |
| `GET /api/v1/wiki/pages/{page_id}` | wiki |
| `GET /api/v1/audit/events` | review action 결과 |

---

## 10. Expected Output Policy

fixture는 입력 파일만 있는 것이 아니라
기대 결과 기준도 함께 가져야 한다.

MVP에서 기대 결과는 아래 4가지 중 하나로 기록한다.

1. expected response payload
2. expected database row shape
3. expected file snapshot
4. expected audit event

예:

- query fixture는 `session created`, `candidate planned`, `learning updated`를 기대 결과로 가진다
- approve fixture는 `candidate_promoted`, `wiki_updated`, `audit event created`를 기대 결과로 가진다

---

## 11. Privacy and Repository Policy

fixture에 대해 아래 규칙을 반드시 지킨다.

1. 실명 금지
- actor는 synthetic id만 사용한다

2. 실강 자료 금지
- 강의노트와 공지는 synthetic markdown으로 작성한다

3. 민감 상담 금지
- counseling 성격 데이터는 MVP fixture에서 제외하거나 매우 제한한다

4. 개인 연락처 금지
- 이메일, 전화번호, 학번 같은 실제값을 넣지 않는다

5. 외부 파일 의존 금지
- 공개 저장소에서 바로 테스트 가능한 텍스트 fixture를 우선한다

---

## 12. Fixture Seed 우선순위

백엔드 구현 직전에 실제로 먼저 만들 fixture는 아래 순서가 가장 좋다.

1. `lecture-note-week-03-chain-rule.md`
2. `announcement-homework-deadline.md`
3. `student-chain-rule-confusion.json`
4. `student-homework-deadline-01.json`
5. `student-homework-deadline-02.json`
6. `open-misconception-chain-rule.json`
7. `open-faq-homework-deadline.json`
8. `approve-homework-faq.json`
9. `concepts-chain-rule.seed.md`
10. `faq-homework-submission.seed.md`
11. `faq-homework-submission.after.md`

이 순서의 이유:

- source 등록
- query 응답
- candidate 생성
- review 승인
- wiki 반영

순으로 MVP의 핵심 흐름이 닫히기 때문이다.

---

## 13. Fixture와 문서의 연결

이 문서는 아래 문서와 직접 연결된다.

1. `docs/product/evaluation-plan.md`
- 어떤 fixture가 acceptance criteria를 검증하는지 연결

2. `docs/product/demo-script.md`
- 데모 전에 무엇을 seed해야 하는지 연결

3. `docs/architecture/api-contracts.md`
- 어떤 endpoint가 어떤 fixture를 소비하는지 연결

4. `docs/architecture/data-contracts.md`
- fixture 내부 필드 형식과 ID 규칙 연결

---

## 14. MVP 이후 확장 기준

MVP 이후 fixture를 늘릴 때도 아래 원칙을 유지한다.

1. 새 역할이 생기면 그 역할용 fixture 세트를 별도로 추가한다
2. 새 endpoint가 생기면 coverage map에 먼저 추가한다
3. 실제 운영 데이터처럼 커지는 fixture dump는 저장소에 직접 넣지 않는다
4. 대형 시나리오보다 작은 검증 가능한 시나리오 묶음을 유지한다

---

## 15. 한 줄 결론

Knowloop MVP fixture catalog는
`synthetic이고 재현 가능하며, raw -> query -> candidate -> review -> wiki 흐름을 끝까지 검증할 수 있는 최소 데이터 세트`
를 저장소 기준으로 고정하는 문서다.
