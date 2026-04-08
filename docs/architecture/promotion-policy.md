# Knowloop Candidate 승격 정책

## 1. 문서 목적

이 문서는 Knowloop에서 생성된 `candidate`를 어떤 기준으로 유지, 병합, 승격, 폐기할지 정의하는 정책 문서다.

이 문서의 목적은 다음과 같다.

- candidate가 formal wiki를 오염시키지 않도록 한다
- 어떤 항목을 공식 지식으로 인정할지 기준을 고정한다
- 사람 승인과 시스템 규칙의 역할을 명확히 나눈다
- 이후 백엔드 구현과 검토 UI가 같은 정책을 따르도록 한다

---

## 2. 기본 철학

Knowloop는 `생성된 정보`보다 `검증 가능한 정보`를 우선한다.

따라서 기본 원칙은 다음과 같다.

1. 학생 질문이나 AI 답변은 바로 formal wiki로 승격하지 않는다.
2. 먼저 candidate로 저장한 뒤 검토한다.
3. formal wiki 승격은 MVP에서 항상 사람 승인을 거친다.
4. source traceability가 없는 항목은 승격하지 않는다.
5. 중복은 merge하고, 불필요하거나 부정확하면 drop한다.

즉, candidate는 “임시 지식 저장소”가 아니라, `품질 게이트가 있는 검토 대기 레이어`다.

---

## 3. 적용 범위

이 정책은 다음 후보 유형에 적용된다.

- `misconception`
- `faq`
- `intervention`
- `unresolved_question`
- `operations_note`

특히 이번 MVP에서 가장 중요하게 다루는 유형은 다음 3가지다.

- `misconception`
- `faq`
- `intervention`

---

## 4. Candidate lifecycle

## 4.1 허용 상태

candidate는 다음 상태 중 하나를 가진다.

- `open`
- `promoted`
- `merged`
- `dropped`

### open
- 검토 대기 상태
- 아직 공식 wiki로 반영되지 않음

### promoted
- 검토와 승인을 거쳐 formal wiki에 반영된 상태

### merged
- 더 적절한 기존 candidate에 병합된 상태

### dropped
- 부정확, 중복 불필요, 가치 낮음 등의 이유로 폐기된 상태

---

## 5. Candidate 생성 규칙

## 5.1 생성 가능한 트리거

다음 상황에서는 candidate 생성이 가능하다.

1. 같은 질문 또는 유사 질문이 반복될 때
2. 학생이 특정 개념을 지속적으로 혼동할 때
3. 교강사가 보충 설명이 필요하다고 판단할 때
4. 미해결 질문이 남았을 때
5. 운영 문의가 반복될 때

## 5.2 생성 최소 조건

candidate는 아래 조건을 만족할 때만 생성한다.

- `kind`가 결정되어야 한다
- `summary`가 있어야 한다
- `source_refs`가 1개 이상 있어야 한다
- `confidence`가 기록되어야 한다
- `class_id`, `course_id`가 있어야 한다

위 조건을 만족하지 못하면:

- candidate를 만들지 않거나
- `failed` audit event를 남기고 생성 보류한다

## 5.3 자동 생성의 위치

자동 생성은 허용되지만, 자동 승격은 허용하지 않는다.

MVP 원칙:

- 시스템은 candidate를 자동 생성할 수 있다
- 시스템은 candidate를 자동 분류할 수 있다
- 시스템은 candidate를 자동 집계할 수 있다
- 시스템은 candidate를 formal wiki로 자동 승격할 수 없다

---

## 6. Candidate 유형별 판정 기준

## 6.1 FAQ 후보

FAQ 후보로 볼 수 있는 조건:

- 같은 질문 또는 매우 유사한 질문이 반복된다
- 질문이 개별 학생의 특수한 사정보다 과목 공통 이슈에 가깝다
- 공식 답변 형태로 정리할 가치가 있다

formal wiki 승격 권장 조건:

- 동일 또는 유사 질문이 3회 이상 반복
- 교강사가 공통 FAQ로 인정
- 관련 source 또는 session trace가 확인 가능

## 6.2 Misconception 후보

오개념 후보로 볼 수 있는 조건:

- 학생이 개념을 반복적으로 잘못 연결한다
- 여러 학생에게 유사한 오해가 나타난다
- 교강사 개입 포인트로 활용 가능하다

formal wiki 승격 권장 조건:

- 단순 오답이 아니라 설명 가능한 오개념 패턴이 있다
- 적어도 1개 이상의 source와 1개 이상의 session 근거가 있다
- 교강사가 “이건 반 전체에 공유할 가치가 있다”고 판단한다

## 6.3 Intervention 후보

개입 후보로 볼 수 있는 조건:

- 다음 수업에서 보충 설명이 필요하다
- 특정 선수지식 부족이 반복된다
- 다음 학습 액션 또는 보충 자료 추천이 가능하다

승격 방향:

- 보통 직접 formal wiki로 가지 않고
- 교강사용 인사이트 또는 보충자료 draft로 먼저 활용한다

## 6.4 Unresolved Question 후보

이 유형은 미해결 질문을 추적하기 위한 상태다.

원칙:

- 바로 FAQ나 misconception으로 승격하지 않는다
- 근거와 답이 명확해지면 다른 kind로 재분류한다

## 6.5 Operations Note 후보

운영 문의/FAQ/공지 충돌 관련 후보다.

원칙:

- 학습 wiki와 운영 wiki는 분리한다
- operations candidate는 `operations` domain으로만 승격 가능하다

---

## 7. 승격 조건

formal wiki로 승격하려면 아래 조건을 모두 만족해야 한다.

1. `status = open`
2. `summary`가 충분히 이해 가능하다
3. `source_refs`가 1개 이상 있다
4. `confidence`가 기록되어 있다
5. 중복 여부 검토가 끝났다
6. 승격 대상 `page_id` 또는 `domain`이 정해졌다
7. 사람 승인자가 승인했다

MVP에서는 위 7개 중 하나라도 빠지면 `promoted` 처리하지 않는다.

---

## 8. 승인 정책

## 8.1 누가 승인할 수 있는가

MVP에서 candidate 승격 승인권자는 다음 둘 중 하나다.

- `instructor`
- `validator`

운영 domain 후보의 경우:

- `operator`가 제안 가능
- `validator` 또는 지정된 관리자 성격의 승인자만 최종 승격 가능

## 8.2 승인 시 반드시 남겨야 할 것

승인 시 아래 정보가 audit에 남아야 한다.

- `candidate_id`
- `approved_by`
- `approved_at`
- `target_page_id` 또는 `target_path`
- `action = candidate_promoted`

## 8.3 사람 승인 없는 자동 승격

MVP에서는 금지한다.

이 정책은 이후에도 기본값으로 유지하되, 추후 일부 `operations` 또는 low-risk FAQ에 대해 예외 검토는 가능하다.

---

## 9. 병합 규칙

candidate는 다음 경우 merge 대상이 된다.

- 제목은 달라도 실제로 같은 질문 패턴을 가리킨다
- source는 다르지만 동일한 오개념을 설명한다
- 이미 더 좋은 summary와 구조를 가진 기존 candidate가 있다

merge 시 원칙:

1. 더 구조가 좋은 candidate를 기준 항목으로 유지한다
2. 병합되는 항목은 `status = merged`
3. `merged_into`에 기준 candidate id를 기록한다
4. source_refs는 기준 candidate에 통합할 수 있다
5. audit event를 남긴다

merge는 삭제가 아니라 관계 기록이다.

---

## 10. 폐기 규칙

candidate는 다음 경우 drop할 수 있다.

1. source 부족으로 검증 불가
2. 단발성 질문으로 공통 가치가 낮음
3. 기존 candidate와 비교했을 때 중복이며 별도 가치가 없음
4. 부정확하거나 오도 가능성이 큼
5. 운영/학습 어느 레이어에도 적합하지 않음

drop 시 원칙:

- `status = dropped`
- drop 이유를 audit에 남긴다
- 원본 source와 session 기록은 삭제하지 않는다

---

## 11. open 상태 유지 규칙

모든 candidate가 반드시 promoted/merged/dropped로 빨리 끝날 필요는 없다.

다음 경우에는 open 상태를 유지한다.

- 근거가 아직 부족함
- 반복성 여부가 더 필요함
- 교강사 검토가 아직 안 끝남
- 아직 FAQ인지 misconception인지 판단이 애매함

즉, `open`은 실패가 아니라 검토 대기 상태다.

---

## 12. 충돌 및 예외 처리

## 12.1 wiki와 충돌하는 경우

이미 formal wiki에 상충하는 정보가 있으면:

- candidate는 자동 승격하지 않는다
- conflict 상태를 audit에 남긴다
- 검토 UI에서 우선적으로 보여준다

## 12.2 confidence가 낮은 경우

confidence가 낮더라도 source가 충분하면 open 상태로 유지할 수 있다.

하지만:

- low confidence candidate는 promoted 전에 추가 검토가 필요하다

## 12.3 source는 있으나 의미가 약한 경우

source가 있다고 해서 자동으로 승격 가치가 생기지 않는다.

반복성, 공통성, 설명 가능성이 부족하면 drop 가능하다.

---

## 13. Audit 기록 정책

candidate lifecycle의 모든 주요 변경은 audit에 남긴다.

반드시 기록할 action:

- `candidate_created`
- `candidate_promoted`
- `candidate_merged`
- `candidate_dropped`
- `candidate_reopened` (추후 필요 시)

권장 추가 필드:

- `reason`
- `actor_role`
- `actor_id`
- `from_status`
- `to_status`
- `notes`

---

## 14. MVP에서 구현 우선순위

이번 MVP에서는 아래 순서로 구현하는 것이 가장 좋다.

1. candidate 생성
2. candidate 목록 조회
3. candidate 승인
4. candidate merge
5. candidate drop
6. candidate와 wiki 연결 이력 보기

즉, 처음부터 복잡한 자동 정책보다 `명시적 lifecycle 관리`를 먼저 만든다.

---

## 15. 대표 예시

## 예시 A. FAQ 승격

- 3명의 학생이 같은 과제 제출 질문을 반복함
- 시스템이 FAQ candidate 생성
- 교강사가 “이건 반 전체 FAQ로 유효하다”고 판단
- validator가 승인
- `data/wiki/faq/...` 페이지 갱신
- candidate status는 `promoted`

## 예시 B. 오개념 merge

- 두 학생이 chain rule과 product rule을 혼동
- 서로 다른 candidate 2개 생성
- 교강사가 같은 오개념 패턴이라고 판단
- 더 잘 정리된 candidate 하나로 merge
- 다른 하나는 `merged`

## 예시 C. 단발성 질문 drop

- 개인 사정에 가까운 일회성 질문
- 과목 공통성 없음
- 운영/학습 위키 어느 쪽에도 자산 가치 낮음
- candidate는 `dropped`

---

## 16. 한 줄 결론

Knowloop MVP의 승격 정책은
`자동 생성은 허용하되 자동 승격은 금지하고, source traceability와 사람 승인을 거친 항목만 formal wiki로 올린다`
를 기본 원칙으로 한다.
