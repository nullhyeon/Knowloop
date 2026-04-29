# Knowloop 역할별 권한 정책

## 1. 문서 목적

이 문서는 Knowloop MVP에서 각 역할이 어떤 데이터를 읽고 쓸 수 있는지 정의하는 권한 정책 문서다.

이 문서의 목적은 다음과 같다.

- 학생, 교강사, 운영자, 검토자, 시스템의 책임을 분리한다
- 데이터 접근 범위를 명확히 해 제품 경계를 고정한다
- 이후 API, 화면, 저장소 설계가 같은 권한 모델을 따르도록 만든다
- 교육 데이터의 민감성을 고려해 기본 접근 원칙을 미리 잠근다

---

## 2. 이 문서의 성격

이 문서는 `인증 구현 문서`가 아니라 `제품 권한 계약 문서`다.

즉, 지금 당장 로그인/권한 시스템을 모두 구현하지 않더라도 아래 원칙은 설계 기준으로 유지한다.

- 어떤 역할이 기본적으로 무엇을 볼 수 있는가
- 어떤 역할이 무엇을 바꿀 수 있는가
- 어떤 행동은 반드시 승인 또는 audit을 남겨야 하는가

현재 MVP 백엔드는 전체 사용자 로그인 시스템 대신 `trusted signed context adapter`를 둔다.
개발에서는 legacy context header를 유지하지만, production 환경은 서명되지 않은
`X-Knowloop-*` 역할/범위 헤더를 신뢰하지 않는다. 정적 context profile registry는
runtime 계약에서 제거되었고, 운영 진입은 인증 또는 signed context에 묶어야 한다.

---

## 3. 기본 원칙

1. 최소 권한 원칙
- 각 역할은 자기 목적을 수행하는 데 필요한 최소 데이터만 읽고 쓴다

2. 학습 데이터와 운영 데이터는 분리한다
- 운영자는 운영 문서를 보되 학생 학습 데이터에 직접 접근하지 않는다

3. 교강사는 집계 정보를 우선 본다
- 학생 개별 원문 session 전체를 기본값으로 보지 않는다
- 먼저 반 단위, 과목 단위 insight를 본다

4. formal wiki 승격은 특권 행동이다
- 승인, 병합, 폐기는 일반 사용자 행동이 아니라 검토 권한 행동으로 본다

5. 특권 행동은 audit을 남긴다
- candidate 승격, 병합, 폐기, 정책성 위키 수정은 모두 기록한다

---

## 4. 역할 정의

MVP에서 다루는 역할은 다음과 같다.

- `student`
- `instructor`
- `operator`
- `validator`
- `system`

### student
- AI에게 질문하고 자기 학습 기록을 보는 사용자

### instructor
- 강의자료를 등록하고 반 단위 insight와 candidate를 검토하는 사용자

### operator
- 공지, 문의, 운영 지식을 관리하는 사용자

### validator
- candidate 승격 품질을 관리하는 검토자 역할

### system
- 자동 생성, 집계, 저장, audit 기록을 수행하는 내부 시스템 역할

---

## 5. 데이터 영역 정의

권한은 아래 데이터 영역을 기준으로 나눈다.

### A. Raw Academic Sources
- 강의자료
- 과제 피드백
- 강의 자막
- 교육용 원본 source

### B. Raw Operational Sources
- 공지 원문
- 운영 메모
- 상담 메모
- 운영 정책 문서

### C. Session Memory
- 학생-AI 질문/답변
- 교강사-AI 준비 대화
- 운영자-AI 운영 대화

### D. Candidate Store
- FAQ 후보
- 오개념 후보
- intervention 후보
- operations 후보

### E. Formal Wiki
- concepts
- faq
- misconceptions
- operations

### F. Learning Layer
- 학생 개인 notes
- gaps
- next actions
- 추후 flashcards

### G. Audit / Meta
- manifest
- lint status
- audit events

---

## 6. 권한 표기 규칙

이 문서에서는 다음 표기를 사용한다.

- `R`: 읽기 가능
- `R-own`: 자기 것만 읽기 가능
- `R-agg`: 집계 결과만 읽기 가능
- `R-scope`: 자신에게 배정된 과목/반/도메인 범위만 읽기 가능
- `W`: 쓰기 가능
- `W-propose`: 제안/후보 생성 가능
- `W-approve`: 승인/병합/폐기 가능
- `W-runtime`: 내부 자동화가 보조 저장과 상태 동기화를 수행할 수 있지만, 사람 승인 없이 최종 승격을 완료할 수는 없음
- `-`: 허용하지 않음

---

## 7. 역할별 권한 매트릭스

| 데이터 영역 | student | instructor | operator | validator | system |
|---|---|---|---|---|---|
| Raw Academic Sources | - | R-scope / W | - | R-scope | R / W |
| Raw Operational Sources | - | - | R-scope / W | R-scope | R / W |
| Session Memory (student) | R-own | R-agg | - | 제한적 R-scope | R / W |
| Session Memory (instructor) | - | R-own | - | - | R / W |
| Session Memory (operator) | - | - | R-own / R-scope | 제한적 R-scope | R / W |
| Candidate Store (academic) | - | R-scope / W-propose / W-approve | - | R-scope / W-approve | R / W-runtime |
| Candidate Store (operations) | - | - | R-scope / W-propose | R-scope / W-approve | R / W-runtime |
| Formal Wiki (course) | R-scope | R-scope / W-propose | - | R-scope / W-approve | R / W-runtime |
| Formal Wiki (operations) | - | - | R-scope / W-propose | R-scope / W-approve | R / W-runtime |
| Learning Layer | R-own | R-agg | - | - | R / W |
| Audit / Meta | - | 제한적 R-scope | 제한적 R-scope | R-scope | R / W |

---

## 8. 역할별 상세 정책

## 8.1 Student

### 읽을 수 있는 것

- 자신의 session memory
- 자신의 learning layer
- 자신이 속한 과목/반에 공개된 formal wiki

### 쓸 수 있는 것

- 질문 제출
- 학습 상호작용 생성

실제 저장은 system이 수행한다.

### 읽을 수 없는 것

- 다른 학생의 session
- 다른 학생의 learning layer
- 검토 전 candidate 목록
- raw source 원문 전체
- 운영 문서

### 설계 의도

student는 결과적으로 자신의 배움이 축적되는 경험을 가져야 하지만,
품질 관리 레이어와 타인의 데이터에 직접 접근해서는 안 된다.

---

## 8.2 Instructor

### 읽을 수 있는 것

- 자신이 담당하는 과목/반의 academic raw sources
- 반 단위 질문 집계와 candidate 목록
- 과목 formal wiki
- 반 단위 learning insight 집계

### 제한적으로 읽을 수 있는 것

- 특정 학생 원문 session 전체는 기본값으로 직접 노출하지 않는다
- 필요한 경우에도 원문보다는 요약, 샘플, 익명화된 예시를 우선한다

### 쓸 수 있는 것

- 강의자료 등록
- academic candidate 제안
- candidate 승인, 병합, 폐기
- wiki 반영 요청

### 읽을 수 없는 것

- 운영 domain raw source
- 운영자 상담 메모
- 다른 과목/반 데이터
- 학생 개인 learning layer 원문 전체

### 설계 의도

교강사는 반 전체 학습 흐름을 보는 역할이지,
학생 개별 기록을 전부 감시하는 역할이 아니다.

따라서 기본 UX와 API는 항상 `집계 먼저, 개별 drill-down은 제한적`으로 설계한다.

---

## 8.3 Operator

### 읽을 수 있는 것

- 운영 공지, 운영 문의, 운영 메모 등 operations domain 자료
- operations candidate
- operations wiki

### 쓸 수 있는 것

- 운영 raw source 등록
- 운영 FAQ 후보 제안
- 공지/문의 구조화 요청

### 읽을 수 없는 것

- 학생 learning layer
- academic session memory
- academic candidate
- 과목 formal wiki 승인 권한

### 설계 의도

운영자는 학습 개입 주체가 아니라 운영 지식 정리 주체다.

운영 효율을 높이는 역할은 중요하지만,
학생 학습 데이터까지 확장 접근하는 것은 MVP 범위에서 금지한다.

---

## 8.4 Validator

### 읽을 수 있는 것

- 자신이 담당하는 범위의 candidate
- 승격 판단에 필요한 source refs
- target formal wiki
- audit 로그 일부

### 쓸 수 있는 것

- candidate 승인
- candidate 병합
- candidate 폐기
- 승격 이력 기록

### 읽을 수 없는 것

- 승격 판단과 무관한 학생 개인 learning layer
- 범위 밖의 raw source 전체

### 설계 의도

validator는 “모든 정보를 다 보는 관리자”가 아니라,
`승격 품질을 관리하는 검토자`로 정의한다.

---

## 8.5 System

### 할 수 있는 것

- session 저장
- candidate 자동 생성
- learning layer 자동 생성
- wiki patch draft 생성
- audit event 기록
- review 목록/상세/patch preview 같은 읽기 성격의 검토 보조

### 할 수 없는 것

- formal wiki 최종 승격을 사람 승인 없이 완료
- review workflow에서 approve / merge / drop / resume-sync를 직접 실행
- 정책 예외를 스스로 결정

### 설계 의도

system은 생산성을 높이는 자동화 계층이지만,
최종 권한자는 아니다.

---

## 9. formal wiki 수정 권한

formal wiki는 아무 역할이나 직접 수정하는 저장소가 아니다.

MVP 기준으로는 다음 흐름만 허용한다.

1. system 또는 사용자 행동으로 candidate 생성
2. instructor 또는 validator 검토
3. 승인 후 wiki patch 반영
4. audit 기록 저장

즉, formal wiki는 항상 `승인 경유 쓰기`를 원칙으로 한다.

---

## 10. Learning Layer 접근 정책

learning layer는 학생 개인화의 핵심이므로 가장 보수적으로 다룬다.

원칙:

- student는 자기 learning layer만 읽는다
- instructor는 학생 개인 원문 대신 집계 결과를 우선 본다
- operator는 learning layer에 접근하지 않는다
- validator도 learning layer를 기본적으로 읽지 않는다

MVP에서 허용하는 instructor 노출 수준:

- 특정 개념에서 몇 명이 막히는지
- 어떤 gap이 반복되는지
- 어떤 개입 포인트가 필요한지

즉, 교강사에게 필요한 것은 개인 사생활 수준의 기록이 아니라,
`수업 개입에 필요한 신호`다.

---

## 11. Session Memory 접근 정책

session memory는 검색 가치가 크지만 민감도도 높다.

원칙:

- student는 자신의 session만 조회 가능
- instructor는 반 전체 집계와 요약을 우선 조회
- operator는 운영 domain session만 조회
- validator는 승격 검토에 필요한 최소 범위만 조회

MVP 기본값:

- 원문 transcript 전체 노출보다 요약과 통계가 우선
- drill-down이 필요하면 audit 대상 행동으로 간주할 수 있다

---

## 12. Candidate 접근 정책

candidate는 학생에게 직접 노출되는 대상이 아니다.

원칙:

- student는 candidate 목록을 직접 보지 않는다
- student에게는 candidate가 아니라 learning 결과로 간접 반영된다
- instructor와 validator는 candidate lifecycle을 관리한다
- operator는 operations candidate만 다룬다

이 정책의 이유:

- candidate는 검토 전 임시 지식이기 때문에
- 사용자에게 공식 정보처럼 노출되면 안 된다

---

## 13. 권한과 UI 연결 규칙

MVP 화면 구조는 권한 정책을 반영해야 한다.

### 학생 화면

- 질문/답변
- 나의 학습 허브
- course wiki 보기

### 교강사 화면

- 반복 질문 대시보드
- 오개념/FAQ candidate 검토함
- wiki 반영 흐름

### 운영자 화면

- 이번 MVP에서는 핵심 화면으로 두지 않음
- 필요 시 최소 운영 후보 화면만 별도 구성

### 검토 화면

- candidate review inbox
- source refs 확인
- approve / merge / drop

---

## 14. Audit이 필요한 행동

아래 행동은 반드시 audit 대상이다.

- candidate 승인
- candidate 병합
- candidate 폐기
- formal wiki 반영
- 운영 domain 정책성 문서 갱신
- 제한적 원문 접근 허용 시의 drill-down

---

## 15. MVP에서 구현 우선순위

권한 정책은 아래 순서로 코드에 반영하는 것이 좋다.

1. student / instructor 화면과 API 분리
2. candidate 검토 권한 분리
3. learning layer 비공개 기본값 반영
4. operations domain 분리
5. audit 대상 액션 기록

즉, 로그인 구현보다 먼저 `역할별 데이터 경계`를 코드 구조에 반영하는 것이 중요하다.

---

## 16. 한 줄 결론

Knowloop MVP의 권한 정책은
`학생은 자신의 학습을 보고, 교강사는 집계와 검토를 담당하며, 운영자는 운영 지식만 다루고, formal wiki 승격은 특권 행동으로 제한한다`
를 기본 원칙으로 한다.
