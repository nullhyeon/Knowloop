"use client";

type ApiEnvelope<T> = {
  status: string;
  data: T;
  meta?: Record<string, unknown>;
  request_id?: string;
};

type LearningSummaryApi = {
  concept_count: number;
  confusion_signal_count: number;
  gap_count: number;
  next_action_count: number;
  session_ref_count: number;
  source_ref_count: number;
  related_wiki_count: number;
  updated_at: string | null;
};

type LearningNoteApi = {
  learning_note_id: string;
  summary: string | null;
  concepts: string[];
  gaps: string[];
  next_actions: string[];
  updated_at: string | null;
  created_at: string;
};

type LearningConfusionSignalApi = {
  signal_id: string;
  title: string;
  summary: string;
  session_ref_count: number;
  state: string;
  linked_session_id: string | null;
};

type LearningNoteCardApi = {
  note_id: string;
  title: string;
  summary: string;
  linked_session_id: string | null;
  linked_session_title: string | null;
  updated_at: string;
  focus_label: string;
  next_action_label: string;
};

type LearningGapCardApi = {
  title: string;
  description: string;
  severity: "focus" | "watch" | "stable";
};

type LearningActionItemApi = {
  title: string;
  description: string;
  target_kind: string;
  target_id: string | null;
};

type LearningRelatedWikiApi = {
  item_id: string;
  page_id: string;
  title: string;
  summary: string;
  reason: string;
};

type LearningRecentSessionApi = {
  session_id: string;
  title: string;
  preview: string;
  created_at: string;
  tags: string[];
  state_label: string;
};

type LearningOverviewApi = {
  summary: LearningSummaryApi;
  learning_note: LearningNoteApi | null;
  confusion_signals: LearningConfusionSignalApi[];
  learning_notes: LearningNoteCardApi[];
  gaps: LearningGapCardApi[];
  next_actions: LearningActionItemApi[];
  related_wiki: LearningRelatedWikiApi[];
  recent_sessions: LearningRecentSessionApi[];
};

export type LearningSummaryTone = "primary" | "review" | "success" | "warning" | "muted";
export type LearningGapSeverity = "focus" | "watch" | "stable";

export type LearningOverview = {
  pageSummary: {
    eyebrow: string;
    title: string;
    description: string;
    badge: string;
  };
  scope: {
    description: string;
  };
  summaryCards: Array<{
    label: string;
    value: string;
    hint: string;
    tone: LearningSummaryTone;
    badge: string;
  }>;
  confusionSignals: Array<{
    signalId: string;
    title: string;
    summary: string;
    sessionCount: number;
    stateLabel: string;
  }>;
  recentNotes: Array<{
    noteId: string;
    title: string;
    summary: string;
    focusLabel: string;
    linkedSessionTitle: string;
    updatedAt: string;
    tags: string[];
  }>;
  gaps: Array<{
    title: string;
    description: string;
    severity: LearningGapSeverity;
  }>;
  nextActions: Array<{
    title: string;
    description: string;
    label: string;
    href?: string;
  }>;
  wikiLinks: Array<{
    itemId: string;
    title: string;
    summary: string;
    reason: string;
    badge: string;
    href?: string;
  }>;
  recentSessions: Array<{
    sessionId: string;
    title: string;
    preview: string;
    createdAt: string;
    tags: string[];
    stateLabel: string;
  }>;
  emptyState: {
    title: string;
    description: string;
  };
};

type LearningFetchContext = {
  profileId: string;
};

const LEARNING_OVERVIEW_PATH = "/api/v1/learning/self";

function buildRequestId(prefix: string): string {
  const suffix =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID().slice(0, 8)
      : `${Date.now()}`;
  return `web-${prefix}-${suffix}`;
}

function buildHeaders(context: LearningFetchContext, requestId?: string): HeadersInit {
  return {
    Accept: "application/json",
    "Content-Type": "application/json",
    "X-Knowloop-Profile-Id": context.profileId,
    "X-Request-Id": requestId ?? buildRequestId("learning"),
  };
}

function appendProfileToHref(href: string, profileId: string): string {
  const separator = href.includes("?") ? "&" : "?";
  return `${href}${separator}profile=${encodeURIComponent(profileId)}`;
}

function formatDateLabel(value: string | null): string {
  if (!value) {
    return "업데이트 정보 없음";
  }

  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat("ko-KR", {
    month: "numeric",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(parsed);
}

function mapStateLabel(state: string): string {
  switch (state) {
    case "needs_review":
      return "집중 복습";
    case "watch":
      return "경과 확인";
    default:
      return "학습 신호";
  }
}

function normalizeLearningOverview(data: LearningOverviewApi, profileId: string): LearningOverview {
  const hasContent =
    data.learning_notes.length > 0 ||
    data.gaps.length > 0 ||
    data.next_actions.length > 0 ||
    data.related_wiki.length > 0 ||
    data.recent_sessions.length > 0 ||
    data.confusion_signals.length > 0;

  const primaryWikiHref = data.related_wiki[0]
    ? appendProfileToHref(`/wiki?page=${encodeURIComponent(data.related_wiki[0].page_id)}`, profileId)
    : undefined;

  return {
    pageSummary: {
      eyebrow: "학습 허브",
      title: hasContent ? "지금 다시 볼 개념과 다음 액션을 정리해 두었습니다." : "아직 학습 데이터가 준비되지 않았습니다.",
      description:
        hasContent
          ? "질문에서 생긴 혼동 신호, 개인 학습 노트, 다음 복습 액션을 한 화면에서 이어 보며 학습 흐름을 유지합니다."
          : "Ask에서 grounded 질문을 시작하면 learning note, gap tracker, next action이 이 화면에 연결됩니다.",
      badge: "학생 전용",
    },
    scope: {
      description:
        "질문에서 쌓인 학습 단서를 다시 읽고, 관련 위키와 다음 액션으로 바로 이어지는 개인 학습 콘솔입니다.",
    },
    summaryCards: [
      {
        label: "추적 중인 개념",
        value: `${data.summary.concept_count}`,
        hint: "현재 learning note에 연결된 핵심 개념 수입니다.",
        tone: "primary",
        badge: "Concepts",
      },
      {
        label: "최근 혼동 신호",
        value: `${data.summary.confusion_signal_count}`,
        hint: "반복적으로 막히는 개념이나 다시 확인해야 하는 지점을 보여줍니다.",
        tone: "warning",
        badge: "Signals",
      },
      {
        label: "다음 액션",
        value: `${data.summary.next_action_count}`,
        hint: "지금 바로 이어서 볼 수 있는 복습/질문 액션입니다.",
        tone: "success",
        badge: "Next",
      },
      {
        label: "관련 위키",
        value: `${data.summary.related_wiki_count}`,
        hint: "공식 위키로 다시 이어져 안정적으로 복습할 수 있는 문서 수입니다.",
        tone: "review",
        badge: "Wiki",
      },
    ],
    confusionSignals: data.confusion_signals.map((signal) => ({
      signalId: signal.signal_id,
      title: signal.title,
      summary: signal.summary,
      sessionCount: signal.session_ref_count,
      stateLabel: mapStateLabel(signal.state),
    })),
    recentNotes: data.learning_notes.map((note) => ({
      noteId: note.note_id,
      title: note.title,
      summary: note.summary,
      focusLabel: note.focus_label,
      linkedSessionTitle: note.linked_session_title ?? "최근 세션",
      updatedAt: formatDateLabel(note.updated_at),
      tags: note.focus_label ? [note.focus_label] : [],
    })),
    gaps: data.gaps,
    nextActions: data.next_actions.map((action) => ({
      title: action.title,
      description: action.description,
      label: action.target_kind === "wiki" ? "위키로 이어가기" : "Ask로 이어가기",
      href:
        action.target_kind === "wiki"
          ? primaryWikiHref
          : appendProfileToHref("/ask", profileId),
    })),
    wikiLinks: data.related_wiki.map((item) => ({
      itemId: item.item_id,
      title: item.title,
      summary: item.summary,
      reason: item.reason,
      badge: "Wiki",
      href: appendProfileToHref(`/wiki?page=${encodeURIComponent(item.page_id)}`, profileId),
    })),
    recentSessions: data.recent_sessions.map((session) => ({
      sessionId: session.session_id,
      title: session.title,
      preview: session.preview,
      createdAt: formatDateLabel(session.created_at),
      tags: session.tags,
      stateLabel: session.state_label,
    })),
    emptyState: {
      title: "아직 학습 기록이 없습니다.",
      description:
        "Ask에서 질문을 시작하면 grounded 답변과 함께 learning note, gaps, next actions가 이 화면에 쌓입니다.",
    },
  };
}

async function fetchEnvelope<T>(path: string, context: LearningFetchContext): Promise<ApiEnvelope<T>> {
  const response = await fetch(path, {
    method: "GET",
    cache: "no-store",
    headers: buildHeaders(context),
  });

  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as
      | { error?: { code?: string; message?: string } }
      | null;
    throw new Error(payload?.error?.message ?? payload?.error?.code ?? `Learning request failed with ${response.status}.`);
  }

  return (await response.json()) as ApiEnvelope<T>;
}

export async function fetchLearningOverview(context: LearningFetchContext): Promise<LearningOverview> {
  const envelope = await fetchEnvelope<LearningOverviewApi>(LEARNING_OVERVIEW_PATH, context);
  return normalizeLearningOverview(envelope.data, context.profileId);
}
