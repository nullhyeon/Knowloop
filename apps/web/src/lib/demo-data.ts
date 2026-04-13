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

export type NextAction = {
  title: string;
  description: string;
  href: string;
};

export type WikiPagePreview = {
  pageId: string;
  title: string;
  summary: string;
  section: string;
  updatedAt: string;
  sourceRefs: string[];
  candidateRefs: string[];
  body: string[];
};

export const navigationItems: NavigationItem[] = [
  { label: "Workspace", href: "/workspace", roles: ["student", "instructor", "operator", "validator"], implemented: true },
  { label: "Ask", href: "/ask", roles: ["student", "instructor"], implemented: true },
  { label: "Learning", href: "/learning", roles: ["student"], implemented: true },
  { label: "Wiki", href: "/wiki", roles: ["student", "instructor", "validator"], implemented: true },
  { label: "Review", href: "/review", roles: ["instructor", "operator", "validator"], implemented: false },
  { label: "Insights", href: "/insights", roles: ["instructor"], implemented: false },
  { label: "Sources", href: "/sources", roles: ["instructor", "operator"], implemented: false },
  { label: "Maintenance", href: "/maintenance", roles: ["operator", "validator"], implemented: false },
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
      "이 흐름은 formal wiki의 개념 설명과 민지의 직전 세션을 함께 사용해 정리된 답변입니다. 다음 슬라이스에서는 오른쪽 패널에서 근거와 write-back 결과를 더 자세하게 펼칩니다.",
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
      "이 응답은 학생용 답변을 그대로 복제하지 않고, 수업 전달용으로 다시 정리된 형태입니다. 이후 candidate 생성 여부와 공식 위키 반영 가능성을 검토하게 됩니다.",
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

export const wikiPages: WikiPagePreview[] = [
  {
    pageId: "page-chain-rule-guide",
    title: "연쇄법칙 핵심 정리",
    summary: "합성 함수 구조를 먼저 식별하고 안쪽 함수의 변화율까지 함께 보는 규칙을 설명합니다.",
    section: "공식 개념",
    updatedAt: "오늘 오전 10:24",
    sourceRefs: ["lecture-note-week-03-chain-rule.md", "student-chain-rule-confusion.json"],
    candidateRefs: ["cand-chain-rule-misconception"],
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
    updatedAt: "어제 오후 6:40",
    sourceRefs: ["announcement-homework-policy.md"],
    candidateRefs: ["cand-homework-faq"],
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
    updatedAt: "2일 전",
    sourceRefs: ["lecture-note-product-rule.md"],
    candidateRefs: [],
    body: [
      "식 안에 함수 두 개가 곱해져 있으면 곱의 미분법을 먼저 의심한다.",
      "한쪽만 미분하고 다른 쪽을 유지하는 두 항의 합 구조를 기억한다.",
      "연쇄법칙과 함께 등장할 때는 안쪽 구조를 먼저 구분한 뒤 규칙을 조합한다.",
    ],
  },
];

export function getProfileById(profileId?: string | null): KnowloopProfile {
  return demoProfiles.find((profile) => profile.profileId === profileId) ?? demoProfiles[0];
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

export function withProfile(href: string, profileId: string): string {
  const params = new URLSearchParams();
  params.set("profile", profileId);
  return `${href}?${params.toString()}`;
}

export function getRecentContextsForProfile(profileId?: string | null): RecentContext[] {
  const profile = getProfileById(profileId);
  return recentContexts.filter((context) => context.profileId === profile.profileId);
}
