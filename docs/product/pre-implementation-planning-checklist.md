# Knowloop 구현 전 기획 체크리스트

## 1. 목적

이 문서는 Knowloop가 현재 가진 강한 아이디어를 실제 구현 가능한 제품 기획으로 더 단단하게 만들기 위해, 코드 작성 전에 확정해야 할 항목을 정리한 체크리스트다.

핵심 원칙은 다음과 같다.

- 방향성 문서와 실행 문서를 분리한다.
- 구현 전에 반드시 고정해야 할 결정을 먼저 잠근다.
- 나중에 바꿔도 되는 것과 지금 정해야 하는 것을 구분한다.

---

## 2. 현재 기획의 강점

현재 문서 기준으로 이미 잘 잡혀 있는 부분은 다음과 같다.

1. 문제 정의가 선명하다.
- 단순 답변형 AI가 아니라 `맥락의 휘발`을 해결한다는 제품 철학이 명확하다.

2. 아키텍처 방향이 좋다.
- `raw -> session -> candidate -> formal wiki -> learning -> maintenance` 흐름이 일관되고 설득력이 있다.

3. 차별점이 분명하다.
- candidate layer와 learning layer를 함께 가져가며 지식 품질과 학습 효과를 동시에 잡으려는 점이 강하다.

4. GitHub와 에이전트 친화적이다.
- 문서, 스키마, 하네스가 이미 분리되어 있어 이후 AI 협업과 구현 추적이 쉽다.

---

## 3. 구현 전에 반드시 확정해야 할 항목

### A. MVP의 정확한 범위

현재 문서는 방향은 좋지만, MVP의 경계가 아직 넓다.

반드시 확정할 것:
- MVP의 주 사용자 1순위는 누구인가
- MVP의 핵심 시나리오 1개는 무엇인가
- MVP에서 실제로 지원할 역할은 어디까지인가
- 운영자 기능은 MVP에 포함할지, 데모용 목업만 둘지
- 학습 개입 기능은 `gap tracker`만 할지, `flashcards`까지 갈지

권장 결정:
- MVP의 주인공은 `수강생 + 교강사`
- 운영자 기능은 `후보 생성과 충돌 탐지` 정도로 제한
- 학습 개입은 `개인 노트 + gap tracker + next actions`까지만 우선 구현

이 항목이 중요한 이유:
- 지금 상태로는 기능 아이디어가 좋아서 계속 범위가 커질 위험이 있다.

### B. 엔터티와 식별자 체계

현재 레이어 구조는 있지만, 실제 구현에 필요한 데이터 엔터티 정의는 부족하다.

반드시 확정할 것:
- `student_id`, `instructor_id`, `operator_id`를 어떤 규칙으로 다룰지
- `course_id`, `class_id`, `term_id`가 모두 필요한지
- `source_id`, `session_id`, `candidate_id`, `page_id`, `learning_note_id`를 어떤 형식으로 만들지
- 한 학생이 여러 과목을 들을 때 learning layer를 어떻게 분리할지

권장 결정:
- MVP에서는 `course_id`, `class_id`, `user_id`만 핵심 키로 사용
- 모든 쓰기 객체는 사람이 읽을 수 있는 slug + timestamp 조합으로 통일

이 항목이 중요한 이유:
- 이 정의가 늦으면 저장 구조와 검색 구조가 계속 흔들린다.

### C. 역할별 권한과 읽기/쓰기 범위

현재 역할 설명은 있으나, 실제 권한 정책은 아직 느슨하다.

반드시 확정할 것:
- Student가 읽을 수 있는 위키 범위
- Instructor가 학생 개인 learning layer를 어디까지 볼 수 있는지
- Operator가 학습 관련 데이터에 접근 가능한지
- Validator 승인 권한은 교강사만 가지는지, 관리자도 가능한지

권장 결정:
- Student: 자신의 session, 자신의 learning, 공개된 course wiki만 읽기
- Instructor: 반 단위 집계와 승인 권한은 갖되, 학생 개인 원문 세션은 제한적 접근
- Operator: 운영 문서와 운영 session만 접근
- Validator: candidate 승격만 담당

이 항목이 중요한 이유:
- 나중에 auth를 붙이더라도, 지금 권한 모델이 없으면 API 설계가 흔들린다.

### D. Candidate 승격 규칙

현재 기획에서 가장 중요한 계층인데, 승격 기준이 아직 선언 수준이다.

반드시 확정할 것:
- 어떤 candidate가 FAQ가 되는지
- 어떤 candidate가 misconception page가 되는지
- 어떤 candidate는 폐기되는지
- source 부족, confidence 부족, 중복일 때의 처리 규칙
- 사람 승인과 규칙 승인 중 어느 것이 필수인지

권장 결정:
- MVP에서는 formal wiki 승격은 모두 사람 승인 필요
- 자동 승격은 금지
- source 1개 이상, summary 필수, confidence 저장 필수
- 중복이면 merge, 출처 부족이면 open 유지, 명백히 부정확하면 drop

이 항목이 중요한 이유:
- 이 규칙이 제품 신뢰도의 핵심이다.

### E. 답변 생성 규칙과 write-back 정책

현재는 답변 후 다시 자산으로 남긴다는 철학은 좋지만, 무엇을 얼마나 남길지는 더 구체화가 필요하다.

반드시 확정할 것:
- 모든 답변이 write-back 되는지
- 특정 조건에서만 candidate를 만들지
- learning layer는 질문마다 갱신할지, 세션 단위로 갱신할지
- 잘못된 답변이 있었을 때 correction loop를 어떻게 돌릴지

권장 결정:
- 모든 답변을 무조건 formal wiki로 반영하지 않는다
- `candidate`는 규칙 기반 생성
- `learning layer`는 학생 단위 세션 종료 시 또는 의미 있는 답변 후 갱신

이 항목이 중요한 이유:
- 너무 많이 쓰면 잡음이 쌓이고, 너무 적게 쓰면 Memory OS 가치가 약해진다.

### F. 성공 기준과 평가 방식

현재 기대 효과는 잘 적혀 있지만, 성공을 측정하는 지표가 없다.

반드시 확정할 것:
- 데모에서 무엇을 성공으로 볼지
- 성능보다 중요한 품질 기준이 무엇인지
- 평가용 질문 세트는 무엇인지
- 교강사 관점에서 유의미한 결과물은 무엇인지

권장 지표:
- 학생 질문 후 관련 session / wiki / learning이 함께 갱신되는지
- 반복 질문 3건 이상이 candidate로 묶이는지
- 교강사가 후보를 승인해 formal wiki에 반영할 수 있는지
- source traceability가 유지되는지

이 항목이 중요한 이유:
- 구현이 끝나도 무엇이 잘된 건지 설명할 근거가 필요하다.

### G. 개인정보 및 안전 범위

현재 `real student PII 금지` 원칙은 있으나 제품 정책 수준의 정의가 부족하다.

반드시 확정할 것:
- 실데이터 대신 fixture만 쓸지
- 익명화 규칙은 무엇인지
- 상담 메모와 운영 메모를 어떤 레벨로 저장할지
- GitHub 공개 저장소에 절대 올라가면 안 되는 데이터 범위

권장 결정:
- MVP 전 과정은 synthetic 또는 anonymized fixture 사용
- raw source 업로드 데모도 샘플 문서만 사용
- 세션/학습 데이터는 사용자 식별자를 가명 처리

이 항목이 중요한 이유:
- 교육 데이터는 민감도가 높아서 나중에 붙이는 정책이 아니라 처음부터 박아야 한다.

---

## 4. 지금 정하면 좋은 항목

### 4.1 첫 데모 시나리오

반드시 한 줄로 정리할 것:
- "학생이 질문한다 -> 이전 기록과 강의자료를 참고한 답변을 받는다 -> candidate와 learning layer가 갱신된다 -> 교강사가 반복 질문을 보고 승인해 위키를 갱신한다"

### 4.2 첫 입력 형식

처음부터 모든 raw source를 지원하지 말고 2개만 고정하는 것이 좋다.

권장:
- 강의자료 markdown 또는 txt 변환본
- 학생 질문/답변 JSON 또는 DB row

### 4.3 첫 검색 우선순위

권장:
- Student query: session -> course wiki -> learning
- Instructor insight: candidate aggregation -> wiki -> raw source

### 4.4 실패 시 동작

반드시 정할 것:
- source 부족 시 답변은 가능하지만 승격은 금지
- wiki 충돌 시 candidate만 생성
- learning layer 생성 실패 시 답변은 제공하되 audit에 기록

---

## 5. 지금 문서에 추가되면 좋은 산출물

구현 전에 아래 문서가 있으면 기획 완성도가 크게 올라간다.

1. `docs/product/mvp-scope.md`
- 진짜 포함 기능 / 제외 기능 / 데모 필수 기능

2. `docs/architecture/data-contracts.md`
- 엔터티 정의, id 규칙, 필수 메타데이터, 파일명 규칙

3. `docs/architecture/promotion-policy.md`
- candidate 생성 조건, 승격 규칙, 폐기 규칙, human-in-the-loop 정책

4. `docs/product/role-permissions.md`
- 역할별 읽기/쓰기 범위와 데이터 접근 제한

5. `docs/product/evaluation-plan.md`
- 데모 시나리오, acceptance criteria, 평가 질문 세트

6. `docs/product/demo-script.md`
- 발표나 시연에서 어떤 흐름으로 보여줄지

---

## 6. 최우선 잠금 순서

코드 구현 전에 아래 순서로 결정하면 가장 효율적이다.

1. MVP의 주 사용자와 핵심 데모 시나리오 고정
2. 엔터티 / 식별자 / 파일명 규칙 고정
3. 역할별 권한 범위 고정
4. candidate 승격 정책 고정
5. 평가 기준과 데모 성공 조건 고정
6. 그 다음 저장소 / API / DB 구현 시작

---

## 7. 한 줄 결론

Knowloop의 큰 방향은 이미 좋다.

지금 가장 필요한 것은 아이디어를 더 늘리는 것이 아니라,
`MVP 경계`, `데이터 계약`, `권한`, `승격 규칙`, `평가 기준`을 먼저 잠가서
구현 과정에서 흔들리지 않게 만드는 것이다.
