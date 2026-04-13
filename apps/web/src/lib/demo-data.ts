export type KnowloopRole = "student" | "instructor" | "operator" | "validator";
export type KnowloopDomain = "academic" | "operations" | "review";

export type NavigationItem = {
  label: string;
  href: string;
  roles: KnowloopRole[];
  implemented: boolean;
};

export type KnowloopProfile = {
  profileId: string;
  label: string;
  role: KnowloopRole;
  actorId: string;
  courseId: string;
  courseLabel: string;
  classId: string;
  classLabel: string;
  domain: KnowloopDomain;
  landingSurface: string;
  description: string;
};

export type SessionPreview = {
  sessionId: string;
  title: string;
  preview: string;
  createdAt: string;
  tags: string[];
  state: "wiki-grounded" | "source-fallback" | "needs-review";
};

export type RecentContext = {
  contextId: string;
  profileId: string;
  title: string;
  summary: string;
  href: string;
  badge: string;
};

export type RetrievalRef = {
  label: string;
  title: string;
  description: string;
};

export type WritebackResult = {
  label: string;
  status: string;
  description: string;
};

export type AskSurface = {
  title: string;
  description: string;
  composerLabel: string;
  composerDraft: string;
  answerTitle: string;
  answerSummary: string;
  answerDetail: string;
  promptExamples: string[];
  rightPanelTitle: string;
  rightPanelDescription: string;
};

export type AnswerBasisSummary = {
  title: string;
  summary: string;
  confidence: string;
  emphasis: string;
  stateLabel: string;
};

export type EvidenceItem = {
  itemId: string;
  objectType: "Wiki Page" | "Source" | "Session";
  title: string;
  summary: string;
  excerpt: string;
  meta: string;
  tone: "grounded" | "supporting" | "fallback";
};

export type RuntimeDetail = {
  label: string;
  value: string;
};

export type LearningUpdate = {
  title: string;
  status: string;
  summary: string;
  highlights: string[];
  nextActionLabel: string;
  nextActionHref: string;
};

export type CandidateOutcome = {
  title: string;
  status: string;
  summary: string;
  targetPage: string;
  confidence: string;
  nextStep: string;
};

export type WritebackStep = {
  objectType: "Session" | "Learning Note" | "Candidate";
  state: string;
  description: string;
};

export type AskPanelData = {
  answerBasis: AnswerBasisSummary;
  evidenceItems: EvidenceItem[];
  runtimeDetails: RuntimeDetail[];
  learningUpdate: LearningUpdate;
  candidateOutcome: CandidateOutcome;
  writebackTrail: WritebackStep[];
};

export type LearningSummaryCard = {
  label: string;
  value: string;
  hint: string;
};

export type LearningGap = {
  title: string;
  description: string;
  severity: "watch" | "focus" | "stable";
};

export type LearningConfusionSignal = {
  signalId: string;
  title: string;
  summary: string;
  frequency: string;
  stateLabel: string;
  href: string;
};

export type LearningNoteEntry = {
  noteId: string;
  title: string;
  summary: string;
  linkedSessionId: string;
  linkedSessionTitle: string;
  updatedAt: string;
  focusLabel: string;
  nextActionLabel: string;
  nextActionHref: string;
};

export type NextAction = {
  title: string;
  description: string;
  href: string;
};

export type LearningWikiLink = {
  itemId: string;
  title: string;
  summary: string;
  reason: string;
  href: string;
};

export type InsightSummaryCard = {
  label: string;
  value: string;
  hint: string;
  tone: "neutral" | "review" | "warning" | "success";
};

export type InsightPattern = {
  patternId: string;
  title: string;
  summary: string;
  signal: string;
  stateLabel: string;
  actionLabel: string;
  href: string;
};

export type InsightPriorityAction = {
  actionId: string;
  title: string;
  summary: string;
  owner: string;
  nextSurface: string;
  href: string;
  tone: "review" | "primary" | "warning";
};

export type SourceRecord = {
  sourceId: string;
  title: string;
  sourceType: "Lecture Note" | "Announcement" | "Policy" | "Class Memo";
  domainLabel: "Academic" | "Operations";
  scopeLabel: string;
  statusLabel: "Registered" | "Needs Sync" | "Active";
  registeredAt: string;
  ownerLabel: string;
  summary: string;
  linkedWikiPages: string[];
  linkedCandidates: string[];
  originLabel: string;
};

export type MaintenanceSeverity = "Error" | "Warning" | "Info";

export type MaintenanceSummaryCard = {
  label: string;
  value: string;
  hint: string;
  tone: "danger" | "warning" | "success" | "neutral";
};

export type MaintenanceFinding = {
  findingId: string;
  title: string;
  severity: MaintenanceSeverity;
  code: string;
  entityType: "Candidate" | "Wiki Page" | "Source Ref" | "Report";
  entityLabel: string;
  summary: string;
  detail: string;
  suggestedAction: string;
};

export type MaintenanceConsoleData = {
  statusLabel: "Healthy" | "Needs Attention" | "Not Run";
  reportState: "report-available" | "read-only-status";
  healthScore: string;
  lastRunAt?: string;
  reviewQueueCount: string;
  summary: string;
  scopeLabel: string;
  reportPath: string;
  generatedBy: string;
  redactionNote?: string;
  summaryCards: MaintenanceSummaryCard[];
  findings: MaintenanceFinding[];
};

export type WikiPagePreview = {
  pageId: string;
  title: string;
  summary: string;
  section: string;
  scopeLabel: string;
  stateLabel: string;
  updatedAt: string;
  sourceRefs: string[];
  candidateRefs: string[];
  relatedPageIds: string[];
  body: string[];
};

export type ReviewPatchLine = {
  lineId: string;
  kind: "context" | "addition" | "removal";
  text: string;
};

export type ReviewAuditEntry = {
  entryId: string;
  label: string;
  actor: string;
  createdAt: string;
  summary: string;
};

export type ReviewAction = {
  action: "approve" | "merge" | "drop" | "resume-sync";
  label: string;
  hint: string;
  tone: "primary" | "secondary" | "danger" | "warning";
};

export type ReviewCandidate = {
  candidateId: string;
  title: string;
  kind: "Misconception" | "FAQ" | "Concept Patch";
  lifecycleState: "Open" | "Pending" | "Promoted" | "Needs Recovery";
  confidence: string;
  confidenceLabel: string;
  summary: string;
  queueNote: string;
  targetPage: string;
  targetPageId: string;
  scopeLabel: string;
  updatedAt: string;
  sourceRefs: string[];
  sessionRefs: string[];
  evidenceNote: string;
  auditEntries: ReviewAuditEntry[];
  patchPreviewTitle: string;
  patchPreviewSummary: string;
  patchLines: ReviewPatchLine[];
  availableActions: ReviewAction[];
};

export const navigationItems: NavigationItem[] = [
  { label: "Workspace", href: "/workspace", roles: ["student", "instructor", "operator", "validator"], implemented: true },
  { label: "Ask", href: "/ask", roles: ["student", "instructor"], implemented: true },
  { label: "Learning", href: "/learning", roles: ["student"], implemented: true },
  { label: "Wiki", href: "/wiki", roles: ["student", "instructor", "validator"], implemented: true },
  { label: "Review", href: "/review", roles: ["instructor", "operator", "validator"], implemented: true },
  { label: "Insights", href: "/insights", roles: ["instructor"], implemented: true },
  { label: "Sources", href: "/sources", roles: ["instructor", "operator", "validator"], implemented: true },
  { label: "Maintenance", href: "/maintenance", roles: ["instructor", "validator"], implemented: true },
];

export const demoProfiles: KnowloopProfile[] = [
  {
    profileId: "student-minji",
    label: "학생 민지",
    role: "student",
    actorId: "stu-kim-minji",
    courseId: "course-calculus-1",
    courseLabel: "미적분 I",
    classId: "class-calculus-1-2026-spring-a",
    classLabel: "A반",
    domain: "academic",
    landingSurface: "/ask",
    description: "개념을 질문하고 학습 기록을 남기는 학생 관점입니다.",
  },
  {
    profileId: "instructor-park",
    label: "강사 박준호",
    role: "instructor",
    actorId: "ins-park-junho",
    courseId: "course-calculus-1",
    courseLabel: "미적분 I",
    classId: "class-calculus-1-2026-spring-a",
    classLabel: "A반",
    domain: "academic",
    landingSurface: "/ask",
    description: "반복 질문과 후보 지식을 검토하는 강사 관점입니다.",
  },
  {
    profileId: "validator-han",
    label: "검토자 한서윤",
    role: "validator",
    actorId: "val-han-seoyun",
    courseId: "course-calculus-1",
    courseLabel: "미적분 I",
    classId: "class-calculus-1-2026-spring-a",
    classLabel: "A반",
    domain: "review",
    landingSurface: "/wiki",
    description: "공식 지식 승격과 정합성을 점검하는 검토자 관점입니다.",
  },
  {
    profileId: "operator-lee",
    label: "운영자 이도윤",
    role: "operator",
    actorId: "ops-lee-doyun",
    courseId: "course-calculus-1",
    courseLabel: "미적분 I",
    classId: "class-calculus-1-2026-spring-a",
    classLabel: "A반",
    domain: "operations",
    landingSurface: "/workspace",
    description: "공지와 운영 자료를 관리하는 운영 관점입니다.",
  },
];

export const defaultProfileId = "student-minji";

const externalProfileAliases: Record<string, string> = {
  "student-minji": "student-minji",
  "instructor-calculus-team": "instructor-park",
  "operator-academic-office": "operator-lee",
  "validator-course-admin": "validator-han",
};

export function normalizeKnownProfileId(profileId?: string | null): string | null {
  if (!profileId) {
    return null;
  }

  return externalProfileAliases[profileId] ?? profileId;
}

export const recentContexts: RecentContext[] = [
  {
    contextId: "ctx-student-recent",
    profileId: "student-minji",
    title: "학생 민지 · Ask 이어서 보기",
    summary: "연쇄법칙과 곱의 미분법 차이를 질문하던 흐름을 이어갑니다.",
    href: "/ask",
    badge: "최근 학습",
  },
  {
    contextId: "ctx-instructor-review",
    profileId: "instructor-park",
    title: "강사 박준호 · FAQ 후보 점검",
    summary: "과제 제출 FAQ와 반복 오개념 후보를 검토하기 위한 진입점입니다.",
    href: "/ask",
    badge: "강의 운영",
  },
  {
    contextId: "ctx-validator-wiki",
    profileId: "validator-han",
    title: "검토자 한서윤 · 위키 근거 확인",
    summary: "공식 위키의 source ref와 candidate ref를 점검하는 흐름입니다.",
    href: "/wiki",
    badge: "검토",
  },
];

export const recentSessions: SessionPreview[] = [
  {
    sessionId: "ses-20260408-114000",
    title: "연쇄법칙과 곱의 미분법이 헷갈리는 이유",
    preview: "공식 위키와 직전 세션을 바탕으로 두 규칙의 적용 기준을 다시 설명한 세션입니다.",
    createdAt: "방금 전",
    tags: ["연쇄법칙", "오개념"],
    state: "wiki-grounded",
  },
  {
    sessionId: "ses-20260408-102200",
    title: "치환적분은 모든 적분에 적용되나요?",
    preview: "위키에 없는 예외 조건이 있어 raw source fallback을 사용한 뒤 기록된 세션입니다.",
    createdAt: "오늘 오전",
    tags: ["적분", "예외"],
    state: "source-fallback",
  },
  {
    sessionId: "ses-20260407-133000",
    title: "합성 함수와 바깥 함수의 순서를 어떻게 보나요?",
    preview: "이전 학습 기록을 기반으로 학습 노트와 다음 복습 액션이 생성된 세션입니다.",
    createdAt: "어제",
    tags: ["복습", "학습노트"],
    state: "needs-review",
  },
];

export const askTopics = ["연쇄법칙", "곱의 미분", "과제 제출 FAQ", "적분 예외", "오개념 정리"];

const askSurfaceByProfile: Record<string, AskSurface> = {
  "student-minji": {
    title: "학생 질문 흐름",
    description:
      "학생이 수업 맥락 안에서 질문하고, grounded answer와 함께 학습 기록이 어떻게 쌓이는지 보여주는 작업 영역입니다.",
    composerLabel: "개념 차이를 분명하게 알고 싶어요",
    composerDraft:
      "연쇄법칙과 곱의 미분법은 어떤 기준으로 먼저 구분하면 좋을까요? 시험에서 빠르게 판단하는 방법도 알려주세요.",
    answerTitle: "현재 답변",
    answerSummary:
      "연쇄법칙은 함수 안에 다른 함수가 들어 있을 때 바깥 함수와 안쪽 함수의 변화율을 연결해서 봅니다. 반면 곱의 미분법은 서로 곱해진 두 함수가 각각 얼마나 변하는지를 따로 계산한 뒤 합쳐서 봅니다.",
    answerDetail:
      "이 답변은 formal wiki의 개념 설명, 민지의 직전 세션, 그리고 강의 source의 예외 조건을 함께 참고해 정리된 grounded answer입니다.",
    promptExamples: [
      "연쇄법칙이 적용되는 식과 곱의 미분법이 적용되는 식을 각각 예시로 보여주세요.",
      "과제 제출 FAQ에서 학생들이 자주 틀리는 규칙을 같이 정리해 주세요.",
    ],
    rightPanelTitle: "근거와 시스템 반응",
    rightPanelDescription:
      "질문이 어떻게 grounded answer로 이어지고, 어떤 학습 기록과 후보 지식이 생성되는지 확인하는 영역입니다.",
  },
  "instructor-park": {
    title: "강사 질의 확인 흐름",
    description:
      "강사가 학생 질문을 재현하거나 자주 묻는 내용을 공식 지식으로 정리하기 전에 확인하는 작업 영역입니다.",
    composerLabel: "반복 질문을 강사용 시선으로 재현해 보기",
    composerDraft:
      "학생들이 연쇄법칙과 곱의 미분법을 헷갈릴 때, 짧고 명확하게 구분해 주는 설명을 만들어주세요. 다음 수업에서 바로 말할 수 있게 정리해 주세요.",
    answerTitle: "강사용 설명 초안",
    answerSummary:
      "학생에게는 먼저 식의 구조를 보라고 안내하면 좋습니다. 함수가 다른 함수 안에 들어가면 연쇄법칙, 함수 둘이 나란히 곱해져 있으면 곱의 미분법이라는 판단 규칙을 먼저 제시하는 방식입니다.",
    answerDetail:
      "이 응답은 학생용 답변을 그대로 복제하지 않고, 수업 전달용으로 다시 정리된 형태입니다. 오른쪽 패널에서는 어떤 근거를 썼는지와 review로 이어질 후보 상태를 함께 확인합니다.",
    promptExamples: [
      "학생들이 자주 하는 오개념을 짧은 피드백 문장으로 바꿔주세요.",
      "다음 수업 도입에서 바로 말할 수 있는 3문장 요약을 만들어주세요.",
    ],
    rightPanelTitle: "근거와 반영 준비",
    rightPanelDescription:
      "공식 위키와 반복 세션을 근거로 candidate를 만들지, 수업 메모로만 남길지 판단하는 영역입니다.",
  },
};

export const retrievalRefs: RetrievalRef[] = [
  {
    label: "Wiki Page",
    title: "연쇄법칙 개념 정리",
    description: "formal wiki를 우선 사용해 개념 차이를 grounded answer basis로 정리했습니다.",
  },
  {
    label: "Session",
    title: "직전 질문 이력",
    description: "같은 학생의 직전 세션을 함께 읽어 반복 오개념과 표현 수준을 맞췄습니다.",
  },
];

export const runtimeSummary = {
  mode: "Teaching mode",
  state: "LLM rewrite",
  fallback: "Wiki grounded",
  note: "최종 응답은 위키와 세션을 기준으로 만들고, 표현만 더 자연스럽게 정리하는 운영 방식입니다.",
};

export const writebackResults: WritebackResult[] = [
  {
    label: "Session",
    status: "registered",
    description: "이번 질문과 답변이 같은 수업 스코프의 새 세션으로 저장됩니다.",
  },
  {
    label: "Learning Note",
    status: "updated",
    description: "연쇄법칙과 곱의 미분법을 구분하는 학습 노트가 갱신될 예정입니다.",
  },
  {
    label: "Candidate",
    status: "open",
    description: "반복되는 오개념 패턴이 candidate로 생성되어 review 흐름으로 이어집니다.",
  },
];

const askPanelDataByProfile: Record<string, AskPanelData> = {
  "student-minji": {
    answerBasis: {
      title: "Answer basis",
      summary:
        "공식 위키의 개념 설명을 우선 사용하고, 직전 세션과 강의 source의 예외 조건을 보조 근거로 연결했습니다.",
      confidence: "높음",
      emphasis: "개념 설명과 시험 판단 기준을 함께 제공하는 grounded answer",
      stateLabel: "Wiki grounded",
    },
    evidenceItems: [
      {
        itemId: "evidence-wiki-chain-rule",
        objectType: "Wiki Page",
        title: "연쇄법칙 핵심 정리",
        summary: "공식 개념 설명과 빠른 판단 기준을 제공한 1차 근거입니다.",
        excerpt: "합성 함수 구조를 먼저 식별하고, 안쪽 함수의 변화율까지 함께 보는 규칙을 기준으로 답변을 정리합니다.",
        meta: "formal wiki · 오늘 오전 10:24 갱신",
        tone: "grounded",
      },
      {
        itemId: "evidence-source-lecture-note",
        objectType: "Source",
        title: "3주차 강의 노트 주석",
        summary: "예외 조건과 시험에서 헷갈리는 패턴을 보조 설명으로 연결했습니다.",
        excerpt: "학생들이 연쇄법칙과 곱의 미분법을 동시에 적용해야 하는 식에서 구조 판단을 먼저 놓치는 경우가 많다는 주석이 포함되어 있습니다.",
        meta: "lecture note source · 첨부 자료",
        tone: "supporting",
      },
      {
        itemId: "evidence-session-minji",
        objectType: "Session",
        title: "직전 질문 이력",
        summary: "민지가 어떤 표현에서 막혔는지 반영해 설명의 밀도와 단어 선택을 맞췄습니다.",
        excerpt: "직전 세션에서도 '식의 구조를 먼저 본다'는 안내가 도움이 되었기 때문에 같은 프레이밍을 유지했습니다.",
        meta: "student session · 방금 전",
        tone: "supporting",
      },
    ],
    runtimeDetails: [
      { label: "Mode", value: "Teaching mode" },
      { label: "Runtime", value: "LLM rewrite" },
      { label: "Fallback", value: "Wiki grounded" },
      { label: "Write-back", value: "Session + Learning Note + Candidate" },
    ],
    learningUpdate: {
      title: "Learning Note update",
      status: "updated",
      summary: "민지의 개인 학습 노트에 연쇄법칙과 곱의 미분법을 구분하는 체크포인트가 추가됩니다.",
      highlights: [
        "식을 보기 전에 함수가 안에 들어 있는지 먼저 확인하기",
        "곱 구조라면 두 항의 변화율을 따로 계산하는 규칙 다시 보기",
        "다음 복습 때 위키 페이지와 예제 식을 함께 다시 읽기",
      ],
      nextActionLabel: "Learning에서 복습 흐름 보기",
      nextActionHref: "/learning",
    },
    candidateOutcome: {
      title: "Candidate result",
      status: "open",
      summary: "학생들이 반복해서 헷갈리는 설명 패턴이 후보 지식으로 열렸습니다.",
      targetPage: "연쇄법칙 핵심 정리",
      confidence: "0.84",
      nextStep: "강사 또는 검토자가 review에서 FAQ/오개념 보강 여부를 판단합니다.",
    },
    writebackTrail: [
      {
        objectType: "Session",
        state: "registered",
        description: "이번 질문과 답변이 현재 수업 맥락의 새 세션으로 저장됩니다.",
      },
      {
        objectType: "Learning Note",
        state: "updated",
        description: "학습 노트에 다음 복습 포인트와 체크리스트가 추가됩니다.",
      },
      {
        objectType: "Candidate",
        state: "open",
        description: "반복 오개념 후보가 review inbox로 이어질 수 있게 생성됩니다.",
      },
    ],
  },
  "instructor-park": {
    answerBasis: {
      title: "Answer basis",
      summary:
        "공식 위키와 반복 질문 세션을 묶어 강사용 설명 초안을 만들고, source에서 확인한 시험 표현을 덧붙였습니다.",
      confidence: "높음",
      emphasis: "학생 설명용 답변을 수업 전달용 문장으로 다시 정리한 grounded draft",
      stateLabel: "Review ready",
    },
    evidenceItems: [
      {
        itemId: "evidence-wiki-chain-rule-instructor",
        objectType: "Wiki Page",
        title: "연쇄법칙 핵심 정리",
        summary: "학생용 개념 설명을 강사용 안내 문장으로 재구성하는 기준 문서입니다.",
        excerpt: "공식 위키의 정의를 짧은 수업 도입 문장으로 바꾸면 학생들이 구조 판단을 먼저 하게 도울 수 있습니다.",
        meta: "formal wiki · 수업 설명 기준",
        tone: "grounded",
      },
      {
        itemId: "evidence-source-class-note",
        objectType: "Source",
        title: "수업 메모와 과제 FAQ source",
        summary: "실제 수업에서 많이 틀린 표현과 과제 전달 방식이 함께 기록된 source입니다.",
        excerpt: "학생들이 '둘 다 미분하면 되는 거 아닌가요?'라고 묻는 빈도가 높아, 판단 규칙을 먼저 주는 방식이 효과적이었습니다.",
        meta: "instructor source · 수업 메모",
        tone: "supporting",
      },
      {
        itemId: "evidence-session-class-pattern",
        objectType: "Session",
        title: "반복 질문 패턴",
        summary: "같은 반 학생들의 질문 패턴을 모아 candidate 생성 근거로 사용했습니다.",
        excerpt: "유사 질문이 세 번 이상 반복되어 FAQ 또는 오개념 정리로 승격할 가치가 있는 패턴으로 보입니다.",
        meta: "class session aggregate · A반",
        tone: "supporting",
      },
    ],
    runtimeDetails: [
      { label: "Mode", value: "Instructor briefing" },
      { label: "Runtime", value: "LLM rewrite" },
      { label: "Grounding", value: "Wiki + session pattern" },
      { label: "Write-back", value: "Session + Candidate" },
    ],
    learningUpdate: {
      title: "Learning Note signal",
      status: "tracked",
      summary: "학생 개인 학습 노트를 직접 수정하지 않고, 반복 질문 패턴을 강사용 메모와 review 근거로 남깁니다.",
      highlights: [
        "학생 설명용 3문장 버전 생성",
        "다음 수업에서 강조할 판단 기준 메모",
        "복습 과제로 연결할 예제 식 후보 정리",
      ],
      nextActionLabel: "Learning 흐름 참고하기",
      nextActionHref: "/learning",
    },
    candidateOutcome: {
      title: "Candidate result",
      status: "pending review",
      summary: "반복 질문 패턴이 수업용 FAQ 또는 오개념 보강 후보로 생성됩니다.",
      targetPage: "연쇄법칙 핵심 정리",
      confidence: "0.89",
      nextStep: "Review에서 patch preview를 확인하고 approve 또는 merge 여부를 결정합니다.",
    },
    writebackTrail: [
      {
        objectType: "Session",
        state: "registered",
        description: "강사용 질의와 답변 초안이 수업 운영 세션으로 남습니다.",
      },
      {
        objectType: "Learning Note",
        state: "tracked",
        description: "학생 개인 노트 대신 강사용 복습 포인트와 다음 수업 메모가 유지됩니다.",
      },
      {
        objectType: "Candidate",
        state: "pending",
        description: "반복 질문 패턴이 공식 지식 보강 후보로 review 흐름에 연결됩니다.",
      },
    ],
  },
};

export const responseModes = [
  { label: "개념 설명 중심", value: "teaching" },
  { label: "짧고 명확하게", value: "concise" },
  { label: "근거 강조", value: "grounded" },
];

export const learningSummaryCards: LearningSummaryCard[] = [
  {
    label: "이번 주 누적 질문",
    value: "12건",
    hint: "연쇄법칙과 곱의 미분 구간에서 가장 많이 질문했습니다.",
  },
  {
    label: "현재 집중 개념",
    value: "연쇄법칙",
    hint: "같은 오개념이 3회 이상 반복되어 우선 복습이 필요합니다.",
  },
  {
    label: "다음 복습 액션",
    value: "2개",
    hint: "예제 복습 1개, 위키 다시 읽기 1개가 추천됩니다.",
  },
];

export const learningGaps: LearningGap[] = [
  {
    title: "함수 구조를 먼저 보는 판단 습관이 약함",
    description: "식을 볼 때 안쪽 함수와 곱 구조를 먼저 구분하는 연습이 더 필요합니다.",
    severity: "focus",
  },
  {
    title: "예외 조건은 raw source로만 기억하고 있음",
    description: "교재의 주석 조건을 위키 개념과 함께 연결해 두면 더 안정적으로 기억할 수 있습니다.",
    severity: "watch",
  },
  {
    title: "최근 복습 리듬은 안정적",
    description: "이전 학습 노트를 다시 읽고 질문으로 이어가는 흐름은 잘 유지되고 있습니다.",
    severity: "stable",
  },
];

export const learningConfusionSignals: LearningConfusionSignal[] = [
  {
    signalId: "signal-chain-rule-structure",
    title: "식을 보기 전에 구조를 먼저 읽는 단계가 자주 빠집니다.",
    summary: "연쇄법칙과 곱의 미분법을 계산 순서로만 구분하려는 패턴이 최근 세션에서 반복되고 있습니다.",
    frequency: "최근 3세션 반복",
    stateLabel: "지금 재설명 필요",
    href: "/ask",
  },
  {
    signalId: "signal-source-exception",
    title: "예외 조건은 기억하지만 공식 위키와 연결되지 않았습니다.",
    summary: "강의 source의 주석 조건은 떠올리지만, 공식 위키의 개념 페이지와 함께 읽지 않아 설명이 흔들리는 구간입니다.",
    frequency: "source fallback 1회",
    stateLabel: "위키 연결 필요",
    href: "/wiki",
  },
];

export const learningNoteEntries: LearningNoteEntry[] = [
  {
    noteId: "note-chain-rule-checkpoint",
    title: "연쇄법칙 판단 체크포인트",
    summary: "함수가 다른 함수 안에 들어 있는지를 먼저 보고, 그다음 바깥 함수와 안쪽 함수의 변화율을 연결하는 순서를 다시 정리했습니다.",
    linkedSessionId: "ses-20260408-114000",
    linkedSessionTitle: "연쇄법칙과 곱의 미분법이 헷갈리는 이유",
    updatedAt: "방금 전",
    focusLabel: "개념 판단 기준",
    nextActionLabel: "Ask에서 같은 질문 다시 풀어보기",
    nextActionHref: "/ask",
  },
  {
    noteId: "note-product-rule-structure",
    title: "곱 구조와 합성 구조를 빠르게 구분하는 법",
    summary: "곱의 미분법은 두 함수가 나란히 곱해진 경우를 먼저 찾고, 연쇄법칙은 함수 안쪽 구조를 먼저 확인하는 흐름으로 비교했습니다.",
    linkedSessionId: "ses-20260407-133000",
    linkedSessionTitle: "합성 함수와 바깥 함수의 순서를 어떻게 보나요?",
    updatedAt: "어제",
    focusLabel: "오개념 교정",
    nextActionLabel: "관련 위키 문서 다시 읽기",
    nextActionHref: "/wiki",
  },
];

export const nextActions: NextAction[] = [
  {
    title: "위키의 연쇄법칙 페이지 다시 읽기",
    description: "공식 개념 요약과 예시를 먼저 훑고 Ask 화면으로 다시 돌아옵니다.",
    href: "/wiki",
  },
  {
    title: "예제 식 3개를 직접 분류해 보기",
    description: "합성 함수인지, 곱 구조인지 먼저 말한 뒤 미분 규칙을 적용해 봅니다.",
    href: "/ask",
  },
  {
    title: "직전 질문 세션 다시 보기",
    description: "비슷한 질문을 어떻게 표현했는지 확인해 오개념 패턴을 줄입니다.",
    href: "/ask",
  },
];

export const learningWikiLinks: LearningWikiLink[] = [
  {
    itemId: "learning-wiki-chain-rule",
    title: "연쇄법칙 핵심 정리",
    summary: "학생 질문에서 가장 자주 다시 열어볼 필요가 있는 공식 개념 페이지입니다.",
    reason: "지금 confusion signal과 직접 연결된 위키",
    href: "/wiki",
  },
  {
    itemId: "learning-wiki-product-rule",
    title: "곱의 미분법 빠른 판단 규칙",
    summary: "연쇄법칙과 함께 비교해서 읽어야 혼동이 줄어드는 quick reference 페이지입니다.",
    reason: "비교 학습용",
    href: "/wiki",
  },
];

export const insightSummaryCards: InsightSummaryCard[] = [
  {
    label: "이번 주 반복 질문",
    value: "18건",
    hint: "연쇄법칙과 곱의 미분법 구간에 질문이 몰려 있습니다.",
    tone: "neutral",
  },
  {
    label: "우선 review 후보",
    value: "3건",
    hint: "바로 공식 지식 보강 여부를 판단해야 하는 candidate 수입니다.",
    tone: "review",
  },
  {
    label: "다음 수업 재설명 필요",
    value: "2개 주제",
    hint: "한 번 더 설명하면 confusion을 크게 줄일 수 있는 주제입니다.",
    tone: "warning",
  },
  {
    label: "최근 반영된 wiki",
    value: "1건",
    hint: "이미 승격된 지식이 있어 다음 수업 자료로 바로 재사용할 수 있습니다.",
    tone: "success",
  },
];

export const insightPatterns: InsightPattern[] = [
  {
    patternId: "pattern-chain-rule",
    title: "연쇄법칙과 곱의 미분법을 구조보다 계산 순서로 구분함",
    summary: "학생들이 식의 형태를 먼저 보지 않고, 무조건 미분을 시작해서 규칙을 섞는 경향이 반복됩니다.",
    signal: "A반 질문 6건 · candidate 1건 생성",
    stateLabel: "Needs reteach",
    actionLabel: "연쇄법칙 위키와 review 후보 같이 보기",
    href: "/review",
  },
  {
    patternId: "pattern-homework-policy",
    title: "과제 제출 마감 이후 재제출 규칙을 강사 답변과 FAQ에서 다르게 기억함",
    summary: "운영 FAQ는 있으나, 실제 수업 중 전달 문장과 FAQ 표현이 미세하게 달라 운영 문의가 계속 반복됩니다.",
    signal: "운영 문의 4건 · FAQ candidate 1건",
    stateLabel: "Review first",
    actionLabel: "운영 FAQ patch preview 열기",
    href: "/review",
  },
  {
    patternId: "pattern-product-rule",
    title: "곱의 미분법 quick guide는 존재하지만 최근 질문 표현을 아직 반영하지 못함",
    summary: "공식 위키가 있으나 최신 설명 패턴이 sync 중단 상태로 남아 있어 validator 확인이 필요합니다.",
    signal: "sync pending 1건",
    stateLabel: "Needs recovery",
    actionLabel: "복구 필요한 candidate 보기",
    href: "/review",
  },
];

export const insightPriorityActions: InsightPriorityAction[] = [
  {
    actionId: "action-reteach-chain-rule",
    title: "다음 수업 도입 5분을 연쇄법칙 판단 규칙 재설명에 사용",
    summary: "식을 보기 전에 구조를 먼저 읽는 한 문장을 수업 첫머리에 넣으면 confusion을 줄일 가능성이 큽니다.",
    owner: "강사 박준호",
    nextSurface: "Ask + Wiki",
    href: "/wiki",
    tone: "primary",
  },
  {
    actionId: "action-review-homework-faq",
    title: "과제 제출 FAQ candidate를 먼저 approve 여부 판단",
    summary: "운영 질문 빈도가 높아, FAQ patch를 확정하면 답변 일관성과 처리 시간을 동시에 개선할 수 있습니다.",
    owner: "운영자/검토자 협업",
    nextSurface: "Review",
    href: "/review",
    tone: "review",
  },
  {
    actionId: "action-resume-product-sync",
    title: "곱의 미분법 sync pending 후보를 resume-sync로 마감",
    summary: "승격은 끝났지만 wiki sync가 끊긴 상태라, 복구를 마쳐야 강사용 공식 지식이 최신 상태로 유지됩니다.",
    owner: "검토자 한서윤",
    nextSurface: "Review",
    href: "/review",
    tone: "warning",
  },
];

export const sourceRecords: SourceRecord[] = [
  {
    sourceId: "src-lecture-note-week-03",
    title: "3주차 강의 노트 주석",
    sourceType: "Lecture Note",
    domainLabel: "Academic",
    scopeLabel: "미적분 I · A반",
    statusLabel: "Active",
    registeredAt: "오늘 오전 9:30",
    ownerLabel: "강사 박준호",
    summary: "연쇄법칙과 곱의 미분법을 함께 설명할 때 자주 발생하는 오개념과 시험 표현을 정리한 강의 주석입니다.",
    linkedWikiPages: ["연쇄법칙 핵심 정리", "곱의 미분법 빠른 판단 규칙"],
    linkedCandidates: ["연쇄법칙 오개념 보강 후보"],
    originLabel: "lecture-note-week-03-chain-rule.md",
  },
  {
    sourceId: "src-homework-policy",
    title: "과제 제출 운영 공지",
    sourceType: "Announcement",
    domainLabel: "Operations",
    scopeLabel: "미적분 I · A반",
    statusLabel: "Active",
    registeredAt: "어제 오후 5:40",
    ownerLabel: "운영자 이도윤",
    summary: "과제 제출 마감, 재제출 승인 조건, 운영 문의 응답 기준이 담긴 공지 source입니다.",
    linkedWikiPages: ["과제 제출 FAQ"],
    linkedCandidates: ["과제 제출 FAQ 보강 후보"],
    originLabel: "announcement-homework-policy.md",
  },
  {
    sourceId: "src-product-rule-memo",
    title: "곱의 미분법 수업 메모",
    sourceType: "Class Memo",
    domainLabel: "Academic",
    scopeLabel: "미적분 I · A반",
    statusLabel: "Needs Sync",
    registeredAt: "2일 전 오후 2:10",
    ownerLabel: "강사 박준호",
    summary: "곱의 미분법 quick guide를 최신 수업 표현으로 보강하기 위한 메모입니다. 현재 sync pending 후보와 연결됩니다.",
    linkedWikiPages: ["곱의 미분법 빠른 판단 규칙"],
    linkedCandidates: ["곱의 미분법 동기화 복구 후보"],
    originLabel: "lecture-note-product-rule.md",
  },
];

const validatorMaintenanceData: MaintenanceConsoleData = {
  statusLabel: "Needs Attention",
  reportState: "report-available",
  healthScore: "82",
  lastRunAt: "오늘 오후 7:18",
  reviewQueueCount: "3",
  summary:
    "현재 스코프에서 stale candidate 1건과 orphan reference 2건이 감지되었습니다. 공식 지식이 깨지기 전에 review와 source traceability를 먼저 복구해야 합니다.",
  scopeLabel: "미적분 I · A반 · Review",
  reportPath: "data/meta/maintenance/course-calculus-1/class-calculus-1-2026-spring-a/lint-status.json",
  generatedBy: "validator scoped report",
  summaryCards: [
    {
      label: "Health score",
      value: "82",
      hint: "차트보다 먼저, 현재 스코프가 운영 가능한 상태인지 읽는 점수입니다.",
      tone: "warning",
    },
    {
      label: "Stale candidate",
      value: "1건",
      hint: "오래 열려 있어 review가 필요한 candidate입니다.",
      tone: "warning",
    },
    {
      label: "Orphan refs",
      value: "2건",
      hint: "위키 또는 source traceability가 끊긴 참조입니다.",
      tone: "danger",
    },
    {
      label: "Review queue",
      value: "3건",
      hint: "현재 maintenance와 함께 같이 정리해야 하는 후보 수입니다.",
      tone: "neutral",
    },
  ],
  findings: [
    {
      findingId: "maint-stale-chain-rule",
      title: "연쇄법칙 오개념 후보가 stale 상태로 오래 열려 있음",
      severity: "Warning",
      code: "stale_candidate",
      entityType: "Candidate",
      entityLabel: "cand-chain-rule-misconception",
      summary: "학생 질문 패턴은 계속 반복되는데 candidate가 3일째 열려 있어 review 우선순위가 높습니다.",
      detail:
        "A반에서 동일한 confusion이 누적되고 있어 공식 위키 보강 시점이 지났습니다. 지금 상태로 두면 Ask와 Insights의 메시지는 유지되지만 공식 지식 반영이 늦어집니다.",
      suggestedAction: "Review에서 candidate를 열고 approve 또는 drop 판단을 먼저 내립니다.",
    },
    {
      findingId: "maint-orphan-source-ref",
      title: "곱의 미분법 위키에서 source ref 하나가 끊어졌습니다",
      severity: "Error",
      code: "orphan_source_ref",
      entityType: "Source Ref",
      entityLabel: "lecture-note-product-rule-v1.md",
      summary: "현재 위키에 적힌 source ref가 manifest에 없는 이전 파일명을 가리키고 있습니다.",
      detail:
        "위키 본문은 유지되고 있지만 근거 경로가 사라져 traceability가 깨졌습니다. validator가 source registry와 wiki meta를 맞춰야 합니다.",
      suggestedAction: "Sources에서 현재 등록된 강의 메모를 확인한 뒤, Review/Wiki에서 연결 ref를 최신 source로 갱신합니다.",
    },
    {
      findingId: "maint-orphan-candidate-ref",
      title: "과제 제출 FAQ 위키에 orphan candidate ref가 남아 있습니다",
      severity: "Error",
      code: "orphan_candidate_ref",
      entityType: "Wiki Page",
      entityLabel: "page-homework-faq",
      summary: "이미 merge 또는 drop된 후보의 ref가 위키 메타에 남아 있어 patch 이력이 혼동될 수 있습니다.",
      detail:
        "운영 FAQ는 최신 상태지만, candidate ref cleanup이 누락되어 review 이력과 위키 메타 사이의 신뢰도가 떨어지고 있습니다.",
      suggestedAction: "Review audit와 wiki meta panel을 함께 열어 stale ref를 제거하고 마지막 sync를 다시 기록합니다.",
    },
  ],
};

const instructorMaintenanceData: MaintenanceConsoleData = {
  statusLabel: "Needs Attention",
  reportState: "read-only-status",
  healthScore: "82",
  lastRunAt: "오늘 오후 7:18",
  reviewQueueCount: "3",
  summary:
    "현재 스코프에 review가 필요한 유지보수 항목이 있습니다. 강사는 상태를 읽을 수 있지만 새 보고서를 생성하거나 민감한 세부 경로를 보지는 않습니다.",
  scopeLabel: "미적분 I · A반 · Academic",
  reportPath: "redacted for instructor view",
  generatedBy: "read-only maintenance status",
  redactionNote: "강사 화면에서는 민감한 entity id와 내부 경로를 가린 요약만 제공합니다.",
  summaryCards: [
    {
      label: "Health score",
      value: "82",
      hint: "지금 수업 운영 관점에서 knowledge health가 완전하지 않다는 신호입니다.",
      tone: "warning",
    },
    {
      label: "Needs reteach + review",
      value: "2개",
      hint: "수업 설명 보강과 review action이 같이 필요한 항목 수입니다.",
      tone: "warning",
    },
    {
      label: "Broken traceability",
      value: "2건",
      hint: "근거 추적이 깨져 validator 도움을 요청해야 하는 상태입니다.",
      tone: "danger",
    },
    {
      label: "Last status sync",
      value: "오늘",
      hint: "이 화면은 최신 persisted maintenance status를 읽습니다.",
      tone: "neutral",
    },
  ],
  findings: [
    {
      findingId: "maint-public-stale",
      title: "오래 열린 candidate가 있어 위키 반영이 늦어지고 있습니다",
      severity: "Warning",
      code: "stale_candidate",
      entityType: "Candidate",
      entityLabel: "redacted",
      summary: "반복 confusion이 이미 확인됐지만 review가 지연되고 있습니다.",
      detail:
        "강사 화면에서는 세부 entity id를 숨기고, 수업 운영상 어떤 종류의 유지보수가 필요한지만 보여줍니다.",
      suggestedAction: "Review 화면에서 validator와 함께 우선순위를 정해 먼저 닫아야 합니다.",
    },
    {
      findingId: "maint-public-orphan-source",
      title: "공식 위키 중 일부가 현재 source traceability를 잃었습니다",
      severity: "Error",
      code: "orphan_source_ref",
      entityType: "Source Ref",
      entityLabel: "redacted",
      summary: "근거 자료와 공식 위키 연결이 끊긴 항목이 있어 강의 자료 재사용 전에 확인이 필요합니다.",
      detail:
        "강사 화면에서는 내부 파일명 대신 어떤 종류의 끊김이 있는지만 보여줍니다. 실제 복구는 validator가 수행합니다.",
      suggestedAction: "Review 또는 Sources 담당자에게 최신 source 연결 상태를 확인해 달라고 요청합니다.",
    },
  ],
};

export const wikiPages: WikiPagePreview[] = [
  {
    pageId: "page-chain-rule-guide",
    title: "연쇄법칙 핵심 정리",
    summary: "합성 함수 구조를 먼저 식별하고 안쪽 함수의 변화율까지 함께 보는 규칙을 설명합니다.",
    section: "공식 개념",
    scopeLabel: "미적분 I · A반 · Academic",
    stateLabel: "Synced",
    updatedAt: "오늘 오전 10:24",
    sourceRefs: ["lecture-note-week-03-chain-rule.md", "student-chain-rule-confusion.json"],
    candidateRefs: ["cand-chain-rule-misconception"],
    relatedPageIds: ["page-product-rule", "page-homework-faq"],
    body: [
      "연쇄법칙은 함수 안에 다른 함수가 들어 있는 합성 구조에서 사용한다.",
      "먼저 바깥 함수의 변화율을 구하고, 그다음 안쪽 함수의 변화율을 곱한다.",
      "학생이 곱의 미분법과 헷갈릴 때는 식의 구조를 먼저 구분하게 돕는 설명이 효과적이다.",
    ],
  },
  {
    pageId: "page-homework-faq",
    title: "과제 제출 FAQ",
    summary: "제출 마감, 수정 가능 범위, 자주 묻는 운영 질문을 공식 답변으로 정리합니다.",
    section: "운영 FAQ",
    scopeLabel: "미적분 I · A반 · Operations",
    stateLabel: "Synced",
    updatedAt: "어제 오후 6:40",
    sourceRefs: ["announcement-homework-policy.md"],
    candidateRefs: ["cand-homework-faq"],
    relatedPageIds: ["page-chain-rule-guide"],
    body: [
      "과제는 마감 전까지 여러 번 수정 제출할 수 있다.",
      "마감 이후에는 운영자 승인 없이는 재제출이 불가능하다.",
      "학생 질문이 반복되면 candidate를 통해 FAQ 페이지가 강화된다.",
    ],
  },
  {
    pageId: "page-product-rule",
    title: "곱의 미분법 빠른 판단 규칙",
    summary: "두 함수가 나란히 곱해진 구조를 빠르게 구분하는 판단 체크리스트입니다.",
    section: "빠른 참고",
    scopeLabel: "미적분 I · A반 · Academic",
    stateLabel: "Needs Review",
    updatedAt: "2일 전",
    sourceRefs: ["lecture-note-product-rule.md"],
    candidateRefs: [],
    relatedPageIds: ["page-chain-rule-guide"],
    body: [
      "식 안에 함수 두 개가 곱해져 있으면 곱의 미분법을 먼저 의심한다.",
      "한쪽만 미분하고 다른 쪽을 유지하는 두 항의 합 구조를 기억한다.",
      "연쇄법칙과 함께 등장할 때는 안쪽 구조를 먼저 구분한 뒤 규칙을 조합한다.",
    ],
  },
];

export const reviewCandidates: ReviewCandidate[] = [
  {
    candidateId: "cand-chain-rule-misconception",
    title: "연쇄법칙 오개념 보강 후보",
    kind: "Misconception",
    lifecycleState: "Open",
    confidence: "0.84",
    confidenceLabel: "높음",
    summary: "학생들이 연쇄법칙과 곱의 미분법을 식의 구조보다 계산 순서로만 구분하는 패턴을 정리한 후보입니다.",
    queueNote: "이번 주 반복 질문 3회 이상",
    targetPage: "연쇄법칙 핵심 정리",
    targetPageId: "page-chain-rule-guide",
    scopeLabel: "미적분 I · A반 · Academic",
    updatedAt: "오늘 오전 11:12",
    sourceRefs: ["lecture-note-week-03-chain-rule.md", "student-chain-rule-confusion.json"],
    sessionRefs: ["ses-20260408-114000", "ses-20260407-133000"],
    evidenceNote: "학생 세션에서 같은 오개념이 반복되어, 공식 개념 설명에 판단 규칙을 추가할 가치가 높은 후보입니다.",
    auditEntries: [
      {
        entryId: "audit-cand-chain-open",
        label: "candidate_opened",
        actor: "system",
        createdAt: "오늘 오전 10:58",
        summary: "반복 질문 패턴을 기반으로 새 candidate가 생성되었습니다.",
      },
      {
        entryId: "audit-cand-chain-scoped",
        label: "class_pattern_detected",
        actor: "강사 박준호",
        createdAt: "오늘 오전 11:03",
        summary: "A반에서 같은 표현이 세 번 이상 반복되어 review 우선순위가 높아졌습니다.",
      },
    ],
    patchPreviewTitle: "연쇄법칙 핵심 정리 patch preview",
    patchPreviewSummary: "판단 기준 문장을 추가해 학생이 식의 구조를 먼저 보도록 유도하는 수정안입니다.",
    patchLines: [
      {
        lineId: "cand-chain-context-1",
        kind: "context",
        text: "연쇄법칙은 함수 안에 다른 함수가 들어 있는 합성 구조에서 사용한다.",
      },
      {
        lineId: "cand-chain-add-1",
        kind: "addition",
        text: "학생 설명에서는 먼저 식을 보고 함수가 다른 함수 안에 들어 있는지 확인하게 하면 곱의 미분법과의 혼동을 줄일 수 있다.",
      },
      {
        lineId: "cand-chain-context-2",
        kind: "context",
        text: "먼저 바깥 함수의 변화율을 구하고, 그다음 안쪽 함수의 변화율을 곱한다.",
      },
    ],
    availableActions: [
      {
        action: "approve",
        label: "Approve",
        hint: "이 candidate를 공식 위키 승격 후보로 확정합니다.",
        tone: "primary",
      },
      {
        action: "merge",
        label: "Merge",
        hint: "기존 후보나 페이지에 병합해 중복을 줄입니다.",
        tone: "secondary",
      },
      {
        action: "drop",
        label: "Drop",
        hint: "근거가 부족하거나 중복이면 후보를 종료합니다.",
        tone: "danger",
      },
    ],
  },
  {
    candidateId: "cand-homework-faq",
    title: "과제 제출 FAQ 보강 후보",
    kind: "FAQ",
    lifecycleState: "Pending",
    confidence: "0.89",
    confidenceLabel: "매우 높음",
    summary: "운영 FAQ에 마감 이후 재제출 조건을 더 명확히 쓰자는 후보입니다.",
    queueNote: "운영 질문 빈도 상위 1위",
    targetPage: "과제 제출 FAQ",
    targetPageId: "page-homework-faq",
    scopeLabel: "미적분 I · A반 · Operations",
    updatedAt: "어제 오후 6:52",
    sourceRefs: ["announcement-homework-policy.md"],
    sessionRefs: ["ses-20260407-ops-001"],
    evidenceNote: "운영 문의가 같은 문장으로 반복되어 FAQ에 추가하면 답변 일관성과 처리 속도를 함께 높일 수 있습니다.",
    auditEntries: [
      {
        entryId: "audit-cand-homework-open",
        label: "candidate_opened",
        actor: "system",
        createdAt: "어제 오후 6:10",
        summary: "운영 문의 반복 패턴에서 FAQ candidate가 생성되었습니다.",
      },
      {
        entryId: "audit-cand-homework-ready",
        label: "patch_preview_ready",
        actor: "운영자 이도윤",
        createdAt: "어제 오후 6:41",
        summary: "공식 FAQ에 바로 반영 가능한 patch preview가 생성되었습니다.",
      },
    ],
    patchPreviewTitle: "과제 제출 FAQ patch preview",
    patchPreviewSummary: "마감 이후 재제출 조건과 승인 주체를 FAQ에 명확히 적는 운영 보강안입니다.",
    patchLines: [
      {
        lineId: "cand-homework-context-1",
        kind: "context",
        text: "과제는 마감 전까지 여러 번 수정 제출할 수 있다.",
      },
      {
        lineId: "cand-homework-removal-1",
        kind: "removal",
        text: "마감 이후에는 재제출이 어렵다.",
      },
      {
        lineId: "cand-homework-add-1",
        kind: "addition",
        text: "마감 이후 재제출은 운영자 승인 후에만 가능하며, 강사 요청만으로는 즉시 반영되지 않는다.",
      },
    ],
    availableActions: [
      {
        action: "approve",
        label: "Approve",
        hint: "운영 FAQ 보강안으로 확정합니다.",
        tone: "primary",
      },
      {
        action: "merge",
        label: "Merge",
        hint: "기존 운영 후보와 통합해 하나의 FAQ 흐름으로 정리합니다.",
        tone: "secondary",
      },
      {
        action: "drop",
        label: "Drop",
        hint: "이미 FAQ에 반영된 내용이면 종료합니다.",
        tone: "danger",
      },
    ],
  },
  {
    candidateId: "cand-product-rule-sync-recovery",
    title: "곱의 미분법 동기화 복구 후보",
    kind: "Concept Patch",
    lifecycleState: "Needs Recovery",
    confidence: "0.76",
    confidenceLabel: "보통",
    summary: "승격은 완료됐지만 wiki sync가 중간에 끊겨 복구가 필요한 후보입니다.",
    queueNote: "resume-sync 필요",
    targetPage: "곱의 미분법 빠른 판단 규칙",
    targetPageId: "page-product-rule",
    scopeLabel: "미적분 I · A반 · Academic",
    updatedAt: "2일 전",
    sourceRefs: ["lecture-note-product-rule.md"],
    sessionRefs: ["ses-20260406-090000"],
    evidenceNote: "승격과 patch preview는 이미 정리됐지만, wiki sync가 끊겨 validator가 resume 흐름으로 마무리해야 하는 상태입니다.",
    auditEntries: [
      {
        entryId: "audit-product-promoted",
        label: "candidate_promoted",
        actor: "검토자 한서윤",
        createdAt: "2일 전 오후 3:08",
        summary: "candidate가 공식 위키 반영 대상으로 승격되었습니다.",
      },
      {
        entryId: "audit-product-sync-pending",
        label: "candidate_wiki_sync_pending",
        actor: "system",
        createdAt: "2일 전 오후 3:08",
        summary: "wiki patch 적용 직전 상태에서 동기화가 pending으로 남았습니다.",
      },
    ],
    patchPreviewTitle: "곱의 미분법 quick guide patch preview",
    patchPreviewSummary: "설명 자체는 승인되었고, 남은 일은 wiki에 안전하게 sync를 마무리하는 것입니다.",
    patchLines: [
      {
        lineId: "cand-product-context-1",
        kind: "context",
        text: "식 안에 함수 두 개가 곱해져 있으면 곱의 미분법을 먼저 의심한다.",
      },
      {
        lineId: "cand-product-add-1",
        kind: "addition",
        text: "학생 설명에서는 '둘이 나란히 곱해진 구조인지 먼저 본다'는 한 줄 판단 문장을 함께 제시한다.",
      },
      {
        lineId: "cand-product-context-2",
        kind: "context",
        text: "연쇄법칙과 함께 등장할 때는 안쪽 구조를 먼저 구분한 뒤 규칙을 조합한다.",
      },
    ],
    availableActions: [
      {
        action: "resume-sync",
        label: "Resume sync",
        hint: "멈춘 wiki sync를 다시 이어서 공식 문서 반영을 완료합니다.",
        tone: "warning",
      },
      {
        action: "drop",
        label: "Drop",
        hint: "복구가 맞지 않다고 판단되면 승격 흐름을 종료합니다.",
        tone: "danger",
      },
    ],
  },
];

export function getProfileById(profileId?: string | null): KnowloopProfile {
  const normalizedProfileId = normalizeKnownProfileId(profileId);
  return demoProfiles.find((profile) => profile.profileId === normalizedProfileId) ?? demoProfiles[0];
}

export function getRoleLabel(role: KnowloopRole): string {
  switch (role) {
    case "student":
      return "학생";
    case "instructor":
      return "강사";
    case "operator":
      return "운영";
    case "validator":
      return "검토";
    default:
      return role;
  }
}

export function getDomainLabel(domain: KnowloopDomain): string {
  switch (domain) {
    case "academic":
      return "Academic";
    case "operations":
      return "Operations";
    case "review":
      return "Review";
    default:
      return domain;
  }
}

export function getNavigationForRole(role: KnowloopRole): NavigationItem[] {
  return navigationItems.filter((item) => item.implemented && item.roles.includes(role));
}

export function getAskSurface(profileId?: string | null): AskSurface {
  const profile = getProfileById(profileId);
  return askSurfaceByProfile[profile.profileId] ?? askSurfaceByProfile[defaultProfileId];
}

export function getAskPanelData(profileId?: string | null): AskPanelData {
  const profile = getProfileById(profileId);
  return askPanelDataByProfile[profile.profileId] ?? askPanelDataByProfile[defaultProfileId];
}

export function withProfile(href: string, profileId: string): string {
  const params = new URLSearchParams();
  params.set("profile", profileId);
  return `${href}?${params.toString()}`;
}

export function getRecentContextsForProfile(profileId?: string | null): RecentContext[] {
  const profile = getProfileById(profileId);
  return recentContexts.filter((context) => context.profileId === profile.profileId);
}

export function getWikiPageById(pageId?: string | null): WikiPagePreview {
  return wikiPages.find((page) => page.pageId === pageId) ?? wikiPages[0];
}

export function getRelatedWikiPages(page: WikiPagePreview): WikiPagePreview[] {
  return page.relatedPageIds
    .map((pageId) => wikiPages.find((candidate) => candidate.pageId === pageId))
    .filter((candidate): candidate is WikiPagePreview => Boolean(candidate));
}

export function getReviewCandidates(profileId?: string | null): ReviewCandidate[] {
  const profile = getProfileById(profileId);

  switch (profile.role) {
    case "operator":
      return reviewCandidates.filter((candidate) => candidate.scopeLabel.includes("Operations"));
    case "validator":
      return reviewCandidates;
    case "instructor":
      return reviewCandidates.filter((candidate) => !candidate.scopeLabel.includes("Operations"));
    default:
      return [];
  }
}

export function getReviewActionsForProfile(
  profileId: string | null | undefined,
  candidate: ReviewCandidate,
): ReviewAction[] {
  const profile = getProfileById(profileId);

  switch (profile.role) {
    case "operator":
      return [];
    case "validator":
      return candidate.availableActions;
    case "instructor":
      return candidate.scopeLabel.includes("Operations") ? [] : candidate.availableActions;
    default:
      return [];
  }
}

export function getSourcesForProfile(profileId?: string | null): SourceRecord[] {
  const profile = getProfileById(profileId);

  switch (profile.role) {
    case "operator":
      return sourceRecords.filter((record) => record.domainLabel === "Operations");
    case "validator":
      return sourceRecords;
    case "instructor":
      return sourceRecords;
    default:
      return [];
  }
}

export function getMaintenanceConsoleData(profileId?: string | null): MaintenanceConsoleData | null {
  const profile = getProfileById(profileId);

  switch (profile.role) {
    case "validator":
      return validatorMaintenanceData;
    case "instructor":
      return instructorMaintenanceData;
    default:
      return null;
  }
}
