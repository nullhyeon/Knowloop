# Knowloop MVP 평가 계획

## 1. 문서 목적

이 문서는 Knowloop MVP가 성공했는지 판단하기 위한 평가 기준을 정의한다.

이 문서의 목적은 다음과 같다.

- 데모에서 반드시 보여야 할 핵심 흐름을 고정한다
- 구현 완료 여부를 기능 목록이 아니라 결과 기준으로 판단한다
- 제품 가치, 데이터 품질, 운영 가능성을 함께 평가한다
- Codex와 Gemini가 같은 성공 기준을 참조하도록 만든다

---

## 2. 평가의 기본 원칙

Knowloop MVP는 단순히 “질문에 답했다”로 성공을 판단하지 않는다.

반드시 함께 증명해야 하는 것은 다음 4가지다.

1. 질문이 사라지지 않고 저장된다
2. 저장된 질문이 구조화된 지식 후보로 이어진다
3. 학습 개입 레이어가 생성된다
4. 교강사 승인으로 공식 wiki가 갱신된다

즉, 평가 기준도 `답변 품질` 단독이 아니라 `질문 -> 축적 -> 검토 -> 승격` 전체 흐름을 기준으로 잡는다.

---

## 3. MVP 성공 정의

MVP는 아래 문장이 참이면 성공으로 본다.

`학생 질문이 session memory, candidate, learning layer, formal wiki로 이어지는 구조가 실제 웹앱과 백엔드에서 재현되고, 교강사가 그 흐름을 검토하고 승인할 수 있다.`

---

## 4. 평가 대상

이번 MVP에서 평가할 대상은 다음과 같다.

### 제품 평가
- 학생 경험
- 교강사 경험
- 구조적 차별성

### 시스템 평가
- 저장 및 추적 가능성
- candidate lifecycle 동작
- wiki 승격 흐름
- audit 가능성

### 문서/설명 평가
- 데모 스토리의 선명함
- source traceability 설명 가능성
- 왜 이것이 단순 챗봇이 아닌지 전달 가능성

---

## 5. 핵심 평가 시나리오

## 5.1 시나리오 A. 학생 질문에서 학습 자산 생성까지

설명:
- 학생이 특정 개념에 대해 질문한다
- 시스템이 답변한다
- session memory가 저장된다
- learning layer가 갱신된다
- candidate가 생성된다

성공 기준:
- 질문/답변이 저장된다
- learning note 또는 gaps / next actions가 생성된다
- candidate가 1개 이상 생성된다
- 모든 결과물에 source trace가 남는다

## 5.2 시나리오 B. 반복 질문이 candidate 집계로 이어지는지

설명:
- 유사한 질문이 여러 학생 또는 같은 학생에게 반복된다
- 시스템이 FAQ 또는 misconception 후보로 묶는다

성공 기준:
- 반복 패턴이 candidate 집계로 나타난다
- 교강사 화면에서 반복 질문 또는 오개념 후보가 보인다
- 단순 raw log 나열이 아니라 구조화된 후보로 보인다

## 5.3 시나리오 C. 교강사 승인으로 formal wiki 갱신

설명:
- 교강사가 candidate를 검토한다
- approve / merge / drop 중 하나를 수행한다
- 승인 시 formal wiki가 업데이트된다

성공 기준:
- candidate 상태 전이가 기록된다
- wiki 반영 결과가 확인된다
- audit event가 남는다

## 5.4 시나리오 D. 갱신된 wiki가 다음 응답에 반영

설명:
- formal wiki가 갱신된 후 유사 질문이 다시 들어온다
- 시스템이 최신 wiki를 참조하여 응답한다

성공 기준:
- 답변이 최신 wiki 기반으로 생성된다
- 이전보다 더 정리된 답변이 가능하다
- source traceability가 유지된다

---

## 6. 평가 축

## 6.1 기능 완성도

질문:
- 핵심 시나리오가 끝까지 연결되는가?
- 중간 단계가 끊기지 않는가?

평가 항목:
- 질문 저장
- session recall
- candidate 생성
- learning layer 생성
- candidate 승인
- wiki 반영

## 6.2 지식 품질

질문:
- formal wiki가 임시 정보로 오염되지 않는가?
- candidate와 wiki가 분리되어 있는가?

평가 항목:
- 승격 전 candidate 보관
- source refs 존재
- 승인 없는 자동 승격 금지
- merge/drop 규칙 작동

## 6.3 학습 지원 품질

질문:
- 학생에게 단순 답변 이상의 가치가 생기는가?

평가 항목:
- 개인 notes 생성
- gaps 생성
- next actions 생성
- “내가 자주 막히는 개념” 표시 가능성

## 6.4 교강사 유용성

질문:
- 교강사가 수업 개입에 쓸 수 있는 정보가 생기는가?

평가 항목:
- 반복 질문 집계
- 오개념 후보 조회
- 승인/반영 workflow
- 보충 포인트 판단 가능성

## 6.5 추적 가능성

질문:
- 모든 주요 산출물이 어디서 왔는지 설명 가능한가?

평가 항목:
- source_refs
- candidate_refs
- audit log
- status transition 기록

---

## 7. 정량/정성 평가 기준

## 7.1 정량 기준

MVP 최소 통과 기준:

1. 대표 데모 시나리오 4개 중 4개 모두 성공
2. candidate 생성 성공률 100% on fixture demo set
3. wiki 승격 흐름 성공률 100% on approval demo set
4. source 없는 wiki 승격 0건
5. 승인 없는 자동 승격 0건

## 7.2 정성 기준

질문:
- 이 서비스가 단순 챗봇이 아니라는 점이 데모에서 자연스럽게 드러나는가?
- 학생 화면과 교강사 화면이 분명히 다른 가치를 보여주는가?
- 설명 없이도 “질문이 자산으로 축적된다”는 느낌이 보이는가?

정성 통과 기준:
- 학생 허브, 교강사 대시보드, candidate review 흐름이 명확히 구분된다
- formal wiki와 candidate 차이가 화면에서 보인다
- 답변 후 어떤 데이터가 갱신되었는지 사용자가 이해할 수 있다

---

## 8. Acceptance Criteria

아래 항목은 구현 완료 체크리스트가 아니라, 제품 acceptance criteria다.

### AC-1 학생 질문 저장
- 학생 질문 1건을 보내면 session record가 생성된다

### AC-2 학습 레이어 갱신
- 질문 이후 learning note 또는 gaps / next actions가 생성된다

### AC-3 candidate 생성
- 의미 있는 질문 흐름에서 candidate가 생성된다

### AC-4 반복 질문 집계
- 유사 질문 3건 이상이 하나의 후보 패턴으로 드러난다

### AC-5 승인 workflow
- 교강사가 candidate를 approve / merge / drop 할 수 있다

### AC-6 wiki 반영
- approve 후 formal wiki가 갱신된다

### AC-7 추적 가능성
- candidate와 wiki 페이지 모두 source refs를 보여줄 수 있다

### AC-8 audit 가능성
- 상태 전이와 승인 이력이 기록된다

### AC-9 권한 경계
- 학생은 candidate 검토 화면을 직접 보지 않는다
- 교강사는 반 단위 insight를 우선 본다

### AC-10 구조 전달력
- 데모만 보아도 이 서비스가 `chat app`이 아니라 `memory workflow app`이라는 점이 드러난다

---

## 9. 평가용 fixture 세트

MVP 평가는 synthetic 또는 anonymized fixture만 사용한다.

필수 fixture 묶음:

1. `course fixture`
- 강의자료 1~2개
- 개념 요약 자료

2. `student session fixture`
- 서로 유사한 질문 3~5개
- 오개념이 드러나는 질문 패턴 2~3개

3. `candidate fixture`
- FAQ 후보
- misconception 후보
- intervention 후보

4. `approval fixture`
- approve 예시 1개
- merge 예시 1개
- drop 예시 1개

5. `wiki fixture`
- concepts page 1개 이상
- faq page 1개 이상

---

## 10. 평가용 질문 세트

평가용 질문은 아래 유형을 포함해야 한다.

### 유형 A. 단일 개념 질문
- 개념 설명 요청
- 수업 자료 참조 여부 확인

### 유형 B. 반복 질문
- 비슷한 오해가 반복되는 패턴 확인

### 유형 C. 선수지식 부족 질문
- misconception 또는 intervention 후보 생성 확인

### 유형 D. 이미 승격된 FAQ 재질문
- wiki 반영 이후 응답 개선 여부 확인

---

## 11. 실패 조건

다음 중 하나라도 발생하면 MVP 핵심 실패로 본다.

1. 질문은 답변되지만 저장이 안 된다
2. candidate가 생성되지만 source trace가 없다
3. candidate와 formal wiki가 구분되지 않는다
4. 승인 없이 formal wiki가 갱신된다
5. learning layer가 생성되지 않는다
6. 교강사가 반복 질문을 볼 수 없다
7. 데모 화면이 사실상 일반 채팅앱과 다르지 않다

---

## 12. 데모 평가 체크리스트

발표 또는 시연 시 아래 순서로 확인한다.

1. 학생 질문 입력
2. 답변 확인
3. session 저장 여부 확인
4. learning layer 갱신 여부 확인
5. candidate 생성 여부 확인
6. 교강사 화면 전환
7. 후보 집계 확인
8. approve / merge / drop 중 하나 실행
9. wiki 업데이트 확인
10. audit 또는 source trace 확인

---

## 13. 구현 검증과 제품 평가의 차이

다음 두 가지는 구분해서 본다.

### 구현 검증
- 테스트 통과
- API 정상 응답
- DB 저장 성공

### 제품 평가
- 사용자가 가치 차이를 느끼는가
- 질문이 지식 자산으로 이어지는가
- 교강사 워크플로가 의미가 있는가

MVP는 두 가지를 모두 통과해야 한다.

---

## 14. 추천 평가 산출물

구현 이후 아래 자료를 남기면 좋다.

1. 데모 시나리오 캡처
2. fixture 기반 통과 로그
3. candidate 전이 예시
4. wiki 반영 전/후 비교
5. source trace 예시

---

## 15. 한 줄 결론

Knowloop MVP의 평가는
`질문에 답했는가`가 아니라
`질문이 저장되고, 구조화되고, 검토되고, 공식 지식으로 승격되는가`
를 증명하는 데 초점을 둔다.
