
type ApiEnvelope<T> = {
  status: string;
  data: T;
  meta?: Record<string, unknown>;
};

type CandidateKindApi = "misconception" | "faq" | "intervention" | "unresolved_question" | "operations_note";

type InsightTopicApi = {
  topic: string;
  session_count: number;
  student_count: number;
};

type InsightGapApi = {
  gap: string;
  student_count: number;
};

type InsightPatternApi = {
  pattern_id: string;
  kind: CandidateKindApi;
  title: string;
  summary: string;
  related_page_id?: string | null;
  candidate_count: number;
  session_count: number;
  student_count: number;
  latest_created_at: string;
  candidate_ids: string[];
  tags: string[];
  max_confidence: number;
};

type InstructorOverviewApi = {
  course_id: string;
  class_id: string;
  student_session_count: number;
  unique_student_count: number;
  open_candidate_total: number;
  candidate_counts: Record<string, number>;
  students_with_learning_notes: number;
  students_with_open_gaps: number;
  top_topics: InsightTopicApi[];
  top_gap_clusters: InsightGapApi[];
  top_patterns: InsightPatternApi[];
};

type InsightsFetchContext = {
  profileId: string;
};

export type InsightSummaryCard = {
  label: string;
  value: string;
  hint: string;
  tone: "neutral" | "review" | "warning" | "success";
};

export type InsightPatternCard = {
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

export type InsightsDashboardData = {
  summaryCards: InsightSummaryCard[];
  patterns: InsightPatternCard[];
  priorityActions: InsightPriorityAction[];
  nextClassBrief: string;
  decisionFraming: string[];
  topicHighlights: string[];
  gapHighlights: string[];
  isEmpty: boolean;
};

function buildHeaders(context: InsightsFetchContext): HeadersInit {
  return {
    Accept: "application/json",
    "X-Knowloop-Profile-Id": context.profileId,
  };
}

async function fetchEnvelope<T>(path: string, init?: RequestInit): Promise<ApiEnvelope<T>> {
  const response = await fetch(path, {
    ...init,
    cache: "no-store",
    headers: {
      ...(init?.headers ?? {}),
      Accept: "application/json",
    },
  });

  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as
      | { error?: { code?: string; message?: string } }
      | null;
    throw new Error(payload?.error?.message ?? payload?.error?.code ?? `Instructor insights request failed with ${response.status}.`);
  }

  return (await response.json()) as ApiEnvelope<T>;
}

function formatCount(value: number): string {
  return new Intl.NumberFormat("ko-KR").format(value);
}

function formatTimestamp(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat("ko-KR", {
    month: "long",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(parsed);
}

function kindLabel(kind: CandidateKindApi): string {
  switch (kind) {
    case "misconception":
      return "오개념";
    case "faq":
      return "FAQ";
    case "intervention":
      return "학습 개입";
    case "unresolved_question":
      return "미해결 질문";
    case "operations_note":
      return "운영 메모";
    default:
      return kind;
  }
}

function buildProfileHref(basePath: string, profileId: string, extraParams?: Record<string, string | null | undefined>): string {
  const params = new URLSearchParams({ profile: profileId });
  Object.entries(extraParams ?? {}).forEach(([key, value]) => {
    if (value) {
      params.set(key, value);
    }
  });
  return `${basePath}?${params.toString()}`;
}

function summarizePatternSignal(pattern: InsightPatternApi): string {
  return `candidate ${formatCount(pattern.candidate_count)}건 · session ${formatCount(pattern.session_count)}건 · 학생 ${formatCount(pattern.student_count)}명`;
}

function stateLabelForPattern(pattern: InsightPatternApi): string {
  if (pattern.kind === "misconception") {
    return "Needs reteach";
  }
  if (pattern.kind === "faq") {
    return "Review first";
  }
  if (pattern.kind === "intervention") {
    return "Teaching action";
  }
  if (pattern.kind === "unresolved_question") {
    return "Needs answer";
  }
  return "Attention";
}

function actionLabelForPattern(pattern: InsightPatternApi): string {
  if (pattern.related_page_id) {
    return "관련 Wiki와 Review 같이 보기";
  }
  return "Review 후보 열기";
}

function hrefForPattern(pattern: InsightPatternApi, profileId: string): string {
  if (pattern.candidate_ids[0]) {
    return buildProfileHref("/review", profileId, { candidate: pattern.candidate_ids[0] });
  }
  if (pattern.related_page_id) {
    return buildProfileHref("/wiki", profileId, { page: pattern.related_page_id });
  }
  return buildProfileHref("/review", profileId);
}

function buildSummaryCards(overview: InstructorOverviewApi): InsightSummaryCard[] {
  return [
    {
      label: "이번 주 학생 세션",
      value: `${formatCount(overview.student_session_count)}건`,
      hint: "현재 반에서 실제로 누적된 학생 질문/답변 세션 수입니다.",
      tone: "neutral",
    },
    {
      label: "우선 review 후보",
      value: `${formatCount(overview.open_candidate_total)}건`,
      hint: "지금 공식 지식 보강 여부를 먼저 판단해야 하는 open candidate 수입니다.",
      tone: overview.open_candidate_total > 0 ? "review" : "success",
    },
    {
      label: "재설명 필요 학생",
      value: `${formatCount(overview.students_with_open_gaps)}명`,
      hint: "학습 note 기준으로 아직 open gap이 남아 있는 학생 수입니다.",
      tone: overview.students_with_open_gaps > 0 ? "warning" : "success",
    },
    {
      label: "학습 흔적 확보 학생",
      value: `${formatCount(overview.students_with_learning_notes)}명`,
      hint: "개인 learning note가 누적되어 다음 수업 개입 근거가 확보된 학생 수입니다.",
      tone: overview.students_with_learning_notes > 0 ? "success" : "neutral",
    },
  ];
}

function buildPatternCards(patterns: InsightPatternApi[], profileId: string): InsightPatternCard[] {
  return patterns.slice(0, 4).map((pattern) => ({
    patternId: pattern.pattern_id,
    title: pattern.title,
    summary: pattern.summary,
    signal: summarizePatternSignal(pattern),
    stateLabel: stateLabelForPattern(pattern),
    actionLabel: actionLabelForPattern(pattern),
    href: hrefForPattern(pattern, profileId),
  }));
}

function buildPriorityActions(
  overview: InstructorOverviewApi,
  patterns: InsightPatternApi[],
  profileId: string,
): InsightPriorityAction[] {
  const actions: InsightPriorityAction[] = [];
  const topPattern = patterns[0] ?? overview.top_patterns[0];
  const faqPattern =
    patterns.find((pattern) => pattern.kind === "faq") ?? overview.top_patterns.find((pattern) => pattern.kind === "faq");

  if (topPattern) {
    actions.push({
      actionId: `action-reteach-${topPattern.pattern_id}`,
      title: `다음 수업 도입에서 ${topPattern.title} 다시 설명`,
      summary: `${summarizePatternSignal(topPattern)}이 반복됐습니다. 먼저 구조 판단 기준이나 핵심 오개념 문장을 다시 짚어 주는 것이 효과적입니다.`,
      owner: "강사",
      nextSurface: "Wiki",
      href: topPattern.related_page_id
        ? buildProfileHref("/wiki", profileId, { page: topPattern.related_page_id })
        : buildProfileHref("/review", profileId, { candidate: topPattern.candidate_ids[0] }),
      tone: "primary",
    });
  }

  if (faqPattern) {
    actions.push({
      actionId: `action-review-${faqPattern.pattern_id}`,
      title: `${kindLabel(faqPattern.kind)} candidate를 먼저 review`,
      summary: `${faqPattern.title}는 반복 문의와 직접 연결되어 있어, 먼저 후보를 정리하면 답변 일관성을 크게 높일 수 있습니다.`,
      owner: "강사 + 검토자",
      nextSurface: "Review",
      href: buildProfileHref("/review", profileId, { candidate: faqPattern.candidate_ids[0] }),
      tone: "review",
    });
  }

  const unresolvedPattern =
    patterns.find((pattern) => pattern.kind === "unresolved_question") ??
    overview.top_patterns.find((pattern) => pattern.kind === "unresolved_question");
  if (unresolvedPattern) {
    actions.push({
      actionId: `action-answer-${unresolvedPattern.pattern_id}`,
      title: "미해결 질문을 공식 위키 보강 후보로 검토",
      summary: `${unresolvedPattern.title}가 아직 공식 지식으로 정리되지 않았습니다. review를 통해 위키 보강이 필요한지 먼저 판단해야 합니다.`,
      owner: "검토자 협업",
      nextSurface: "Review",
      href: buildProfileHref("/review", profileId, { candidate: unresolvedPattern.candidate_ids[0] }),
      tone: "warning",
    });
  }

  return actions.slice(0, 3);
}

function buildNextClassBrief(overview: InstructorOverviewApi): string {
  const topTopic = overview.top_topics[0]?.topic;
  const topGap = overview.top_gap_clusters[0]?.gap;

  if (topTopic && topGap) {
    return `다음 수업은 ${topTopic} 관련 질문이 반복된 이유를 먼저 짚고, 특히 “${topGap}”를 짧은 판단 문장으로 다시 설명하는 방향이 좋습니다.`;
  }

  if (topTopic) {
    return `다음 수업에서는 ${topTopic} 주제를 먼저 다시 열어, 반복 질문이 생긴 배경을 짧게 정리하는 것이 좋습니다.`;
  }

  if (topGap) {
    return `지금은 “${topGap}”를 다시 설명하는 것이 가장 우선입니다. 개념 요약보다 판단 기준을 먼저 말하는 구성이 좋습니다.`;
  }

  return "아직 충분한 학생 활동이 쌓이지 않아 우선 재설명 주제를 자동으로 제안할 수 없습니다. Ask와 Learning 데이터가 더 쌓이면 다음 수업 요약이 구체화됩니다.";
}

function buildDecisionFraming(overview: InstructorOverviewApi, patterns: InsightPatternApi[]): string[] {
  const lines: string[] = [];

  if (overview.top_topics[0]) {
    lines.push(`가장 반복된 주제는 ${overview.top_topics[0].topic}이며, 세션 ${formatCount(overview.top_topics[0].session_count)}건에서 다시 등장했습니다.`);
  }
  if (overview.top_gap_clusters[0]) {
    lines.push(`가장 크게 남은 gap은 “${overview.top_gap_clusters[0].gap}”이고 학생 ${formatCount(overview.top_gap_clusters[0].student_count)}명에게서 확인됩니다.`);
  }
  if (patterns[0]) {
    lines.push(`가장 먼저 review할 패턴은 ${patterns[0].title}이며, 최신 신호는 ${formatTimestamp(patterns[0].latest_created_at)} 기준입니다.`);
  }

  if (!lines.length) {
    return ["충분한 학생 활동이 누적되면 이 화면이 다음 수업 우선순위를 더 선명하게 제안합니다."];
  }

  return lines;
}

function buildTopicHighlights(topics: InsightTopicApi[]): string[] {
  return topics
    .slice(0, 3)
    .map((topic) => `${topic.topic} · 세션 ${formatCount(topic.session_count)}건 · 학생 ${formatCount(topic.student_count)}명`);
}

function buildGapHighlights(gaps: InsightGapApi[]): string[] {
  return gaps.slice(0, 3).map((gap) => `${gap.gap} · 학생 ${formatCount(gap.student_count)}명`);
}

export async function fetchInsightsDashboard(context: InsightsFetchContext): Promise<InsightsDashboardData> {
  const [overviewEnvelope, patternsEnvelope] = await Promise.all([
    fetchEnvelope<InstructorOverviewApi>("/api/v1/instructor/insights/overview", {
      headers: buildHeaders(context),
    }),
    fetchEnvelope<InsightPatternApi[]>("/api/v1/instructor/insights/patterns?limit=6&offset=0", {
      headers: buildHeaders(context),
    }),
  ]);

  const overview = overviewEnvelope.data;
  const patterns = patternsEnvelope.data;

  const isEmpty =
    overview.student_session_count === 0 &&
    overview.open_candidate_total === 0 &&
    overview.students_with_learning_notes === 0 &&
    patterns.length === 0;

  return {
    summaryCards: buildSummaryCards(overview),
    patterns: buildPatternCards(patterns, context.profileId),
    priorityActions: buildPriorityActions(overview, patterns, context.profileId),
    nextClassBrief: buildNextClassBrief(overview),
    decisionFraming: buildDecisionFraming(overview, patterns),
    topicHighlights: buildTopicHighlights(overview.top_topics),
    gapHighlights: buildGapHighlights(overview.top_gap_clusters),
    isEmpty,
  };
}

