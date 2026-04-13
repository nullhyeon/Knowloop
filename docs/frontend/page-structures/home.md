# Page Structure: `/`

## Purpose

Introduce Knowloop clearly and help judges start with seeded sample data immediately.

This page is not a generic marketing landing page.
It is a product-entry page for a live demo environment.

Implementation note:

- the current live root route may still redirect into `/workspace` until this slice is implemented
- this document defines the target contract for the next homepage build

The page must explain three things quickly:

1. what Knowloop is
2. how the workflow works
3. where the judge should click first

---

## Primary Users

- judges
- first-time evaluators
- demo viewers

Secondary users:

- teammates opening the deployed product for review

---

## Core Job

Answer:

`What does this product do, why is it different from a chatbot, and which sample experience should I open first?`

---

## Reference Direction

Use this blend:

- `Linear` for hero discipline, spacing, and product confidence
- `GitBook` for the workflow section and maintained knowledge messaging
- `NotebookLM` Korean product tone for evidence-based AI explanation
- `Slite` for trust, maintenance, and knowledge quality messaging
- `Vercel` only for subtle operational trust language

Do not build a glossy startup landing page.
Do not build a playful edtech homepage.
Do not build a centered AI chat hero.

---

## Layout

### Product Entry Sequence

- top: concise hero with one strong headline, one support paragraph, and product screenshot or product collage
- second: `How it works` sequence with 4-5 steps
- third: two seeded sample entry cards
- fourth: trust section explaining evidence, review gate, and maintained wiki
- optional final strip: compact note about Korean education workflow fit

---

## Required Sections

### 1. Hero

Must communicate:

- Knowloop is an education knowledge operations system
- questions turn into durable learning and wiki artifacts
- this is not just another chatbot

The CTA area must prioritize:

- `학생용 샘플 데이터로 시작`
- `교강사용 샘플 데이터로 시작`

There should not be more than two primary buttons in the first viewport.

### 2. Why Knowloop

Use 3 compact value cards or bullets:

- grounded answers with visible evidence
- candidate review before official promotion
- learning notes and class-level insight from real question history

### 3. How It Works

Required workflow:

- 질문
- 축적
- 검토
- 승격
- 탐색

Suggested copy direction:

- 학생이 질문한다
- 세션, 학습 노트, 후보 지식이 생성된다
- 교강사가 후보 지식을 검토한다
- 공식 위키가 갱신된다
- 다음 질문부터 더 안정적인 답변을 제공한다

### 4. Seeded Demo Entry

Show exactly two role-entry cards:

#### Student sample start

- button label: `학생용 샘플 데이터로 시작`
- supporting text: explain that the viewer will see Ask, Learning, and Wiki with pre-seeded study history

#### Instructor sample start

- button label: `교강사용 샘플 데이터로 시작`
- supporting text: explain that the viewer will see Insights, Review, and Wiki with pre-seeded class patterns

Rules:

- cards should feel trustworthy and product-like
- make the difference between the two sample experiences obvious
- do not mention operator as a primary entry on this page

### 5. Trust and Quality

Must explain:

- official answers are grounded in maintained wiki context
- uncertain knowledge becomes `Candidate` before promotion
- review and maintenance keep the knowledge base healthy

This section should feel calm and precise, not defensive.

---

## Required Data

The page itself may use static explanatory copy.
The entry buttons must map to canonical sample profiles already supported by the context bootstrap flow.

Expected target behavior:

- student sample button deep-links into a seeded student profile
- instructor sample button deep-links into a seeded instructor profile

---

## Required UI Elements

- hero headline
- hero support copy
- product image area
- 4-5 step workflow row
- two role-entry cards
- trust/value strip

Optional:

- compact footer note
- "이미 준비된 샘플 데이터로 바로 체험할 수 있습니다" notice

---

## Copy Rules

- Korean-first copy
- short sentences
- avoid inflated startup language
- keep AI terminology grounded
- do not overuse English nouns
- allow natural product nouns such as `Ask`, `Wiki`, `Review`

Good tone:

- `질문이 쌓일수록 더 정교해지는 수업 지식 운영 시스템`
- `답변만 제공하지 않고, 학습 노트와 후보 지식을 함께 남깁니다`

Bad tone:

- `혁신적인 생성형 AI 플랫폼`
- `차세대 지능형 교육 솔루션`

---

## States

### Loading

- not important for static hero content
- if profile/bootstrap metadata is needed, keep loading minimal and quiet

### Empty

- not applicable as a primary pattern

### Error

- if sample entry metadata fails, keep the message short and action-oriented
- do not show technical backend wording on the hero

---

## Guardrails

- do not make the page feel unrelated to the authenticated console
- do not bury the sample entry buttons under long feature sections
- do not overexplain architecture before the viewer sees the product
- do not treat the page as a generic signup screen
- do not overuse gradient backgrounds or decorative AI imagery

---

## Success Condition

In under one minute, a judge should understand:

1. this is not just a chatbot
2. the product turns questions into maintained knowledge
3. they can start with either student or instructor sample data immediately
