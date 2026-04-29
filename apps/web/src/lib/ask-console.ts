"use client";

import { buildKnowloopContextHeaders, type KnowloopRole } from "@/lib/workspace-context";

type ApiEnvelope<T> = {
  status: string;
  data: T;
  meta?: Record<string, unknown>;
  request_id?: string;
};

type SessionVisibilityApi = "own" | "class_redacted";
type ResponseModeApi = "default" | "concise" | "teaching" | "review";
type RetrievalEntityTypeApi = "wiki_page" | "session" | "raw_source" | "learning_note";
type RetrievalReasonApi =
  | "high_relevance"
  | "recent_related_context"
  | "fallback_match"
  | "personal_learning_state";

type SessionSearchHitApi = {
  session_id: string;
  role: KnowloopRole;
  created_at: string;
  tags: string[];
  candidate_ref_count: number;
  learning_note_ref_count: number;
  source_ref_count: number;
  visibility: SessionVisibilityApi;
  match_summary: string;
  question_preview?: string | null;
  answer_preview?: string | null;
};

type QueryRetrievalRefApi = {
  entity_type: RetrievalEntityTypeApi;
  entity_id: string;
  reason: RetrievalReasonApi | string;
  source_refs: Array<{
    source_id?: string;
    source_type?: string;
    chunk_id?: string;
  }>;
};

type QueryWritebackPlanItemApi = {
  kind: "session" | "learning_note" | "candidate" | string;
  action: string;
  status: string;
  target_id: string;
  explanation: string;
};

type QueryResponseApi = {
  answer: string;
  answer_basis: string[];
  retrieval_refs: QueryRetrievalRefApi[];
  writeback_plan: QueryWritebackPlanItemApi[];
  session_id: string;
  created_at: string;
};

type QueryRuntimeMetaApi = {
  answer_source?: "llm_rewrite" | "deterministic_fallback" | string;
  stored_answer_source?: "deterministic_fallback" | string;
  llm_enabled?: boolean;
  llm_applied?: boolean;
  provider?: string | null;
  configured_model?: string | null;
};

type AskFetchContext = {
  contextId: string;
};

export type AskResponseMode = ResponseModeApi;

export type AskResponseModeOption = {
  value: AskResponseMode;
  label: string;
  description: string;
};

export type AskSessionHistoryState = "candidate-linked" | "learning-linked" | "source-linked";

export type AskSessionHistoryItem = {
  sessionId: string;
  title: string;
  preview: string;
  detailPreview: string | null;
  createdAt: string;
  rawCreatedAt: string;
  tags: string[];
  state: AskSessionHistoryState;
  stateLabel: string;
  visibility: SessionVisibilityApi;
  matchSummary: string;
  candidateRefCount: number;
  learningNoteRefCount: number;
  sourceRefCount: number;
};

export type AskEvidenceTone = "grounded" | "supporting" | "fallback";

export type AskEvidenceItem = {
  itemId: string;
  objectType: "Wiki Page" | "Source" | "Session" | "Learning Note";
  title: string;
  summary: string;
  excerpt: string;
  meta: string;
  tone: AskEvidenceTone;
  href?: string;
};

export type AskPanelData = {
  answerBasis: {
    title: string;
    summary: string;
    stateLabel: string;
    emphasis: string;
    basisTags: string[];
  };
  evidenceItems: AskEvidenceItem[];
  runtimeDetails: Array<{
    label: string;
    value: string;
  }>;
  learningUpdate: {
    title: string;
    status: string;
    summary: string;
    highlights: string[];
    nextActionLabel: string;
    nextActionHref: string;
  };
  candidateOutcome: {
    title: string;
    status: string;
    summary: string;
    targetLabel: string;
    nextStep: string;
    href?: string;
  };
  writebackTrail: Array<{
    objectType: "Session" | "Learning Note" | "Candidate";
    state: string;
    description: string;
  }>;
};

export type AskConversationResult = {
  question: string;
  sessionId: string;
  createdAt: string;
  answer: string;
  answerTitle: string;
  answerSummary: string;
  answerDetail: string | null;
  answerBadge: string;
  panelData: AskPanelData;
};

const RESPONSE_MODE_OPTIONS: AskResponseModeOption[] = [
  { value: "teaching", label: "Teaching", description: "학생 설명에 맞춘 단계형 응답" },
  { value: "default", label: "Default", description: "현재 위키와 세션 맥락을 균형 있게 반영" },
  { value: "concise", label: "Concise", description: "짧고 빠르게 핵심만 답변" },
  { value: "review", label: "Review", description: "검토/운영 관점으로 요약" },
];

function buildHeaders(
  context: AskFetchContext,
  options?: {
    idempotencyKey?: string;
    requestId?: string;
  },
): HeadersInit {
  return {
    Accept: "application/json",
    "Content-Type": "application/json",
    ...buildKnowloopContextHeaders(context.contextId),
    "X-Request-Id": options?.requestId ?? buildRequestId("ask"),
    ...(options?.idempotencyKey ? { "Idempotency-Key": options.idempotencyKey } : {}),
  };
}

function buildRequestId(prefix: string): string {
  const suffix =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID().slice(0, 8)
      : `${Date.now()}`;
  return `web-${prefix}-${suffix}`;
}

function appendContextToHref(href: string, contextId: string): string {
  const separator = href.includes("?") ? "&" : "?";
  return `${href}${separator}context=${encodeURIComponent(contextId)}`;
}

export function createAskMutationIdempotencyKey(): string {
  const suffix =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `web-query-${suffix}`;
}

async function fetchEnvelope<T>(path: string, init: RequestInit): Promise<ApiEnvelope<T>> {
  const response = await fetch(path, {
    ...init,
    cache: "no-store",
  });

  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as
      | { error?: { code?: string; message?: string } }
      | null;
    throw new Error(payload?.error?.message ?? payload?.error?.code ?? `Ask request failed with ${response.status}.`);
  }

  return (await response.json()) as ApiEnvelope<T>;
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

function truncatePreview(value: string, maxLength = 42): string {
  const normalized = value.trim().replace(/\s+/g, " ");
  if (normalized.length <= maxLength) {
    return normalized;
  }
  return `${normalized.slice(0, maxLength - 1)}…`;
}

function formatSessionState(hit: SessionSearchHitApi): {
  state: AskSessionHistoryState;
  stateLabel: string;
} {
  if (hit.candidate_ref_count > 0) {
    return { state: "candidate-linked", stateLabel: "Candidate 있음" };
  }

  if (hit.learning_note_ref_count > 0) {
    return { state: "learning-linked", stateLabel: "학습 반영" };
  }

  return { state: "source-linked", stateLabel: "Source 연결" };
}

function buildSessionTitle(hit: SessionSearchHitApi): string {
  if (hit.visibility === "class_redacted") {
    return hit.tags.length
      ? `학생 세션 · ${hit.tags[0]}`
      : `학생 세션 · ${formatTimestamp(hit.created_at)}`;
  }

  if (hit.question_preview?.trim()) {
    return truncatePreview(hit.question_preview);
  }

  if (hit.answer_preview?.trim()) {
    return truncatePreview(hit.answer_preview);
  }

  return `Session ${hit.session_id.slice(-8)}`;
}

function buildSessionPreview(hit: SessionSearchHitApi): string {
  if (hit.visibility === "class_redacted") {
    return hit.match_summary;
  }

  return hit.question_preview?.trim() || hit.answer_preview?.trim() || hit.match_summary;
}

function buildSessionDetailPreview(hit: SessionSearchHitApi): string | null {
  if (hit.visibility === "class_redacted") {
    return hit.tags.length ? `태그 · ${hit.tags.join(" · ")}` : null;
  }

  return hit.answer_preview?.trim() || null;
}

function mapSessionHit(hit: SessionSearchHitApi): AskSessionHistoryItem {
  const { state, stateLabel } = formatSessionState(hit);
  return {
    sessionId: hit.session_id,
    title: buildSessionTitle(hit),
    preview: buildSessionPreview(hit),
    detailPreview: buildSessionDetailPreview(hit),
    createdAt: formatTimestamp(hit.created_at),
    rawCreatedAt: hit.created_at,
    tags: hit.tags,
    state,
    stateLabel,
    visibility: hit.visibility,
    matchSummary: hit.match_summary,
    candidateRefCount: hit.candidate_ref_count,
    learningNoteRefCount: hit.learning_note_ref_count,
    sourceRefCount: hit.source_ref_count,
  };
}

function formatAnswerBasisLabel(label: string): string {
  switch (label) {
    case "formal_wiki":
      return "Formal Wiki";
    case "session_context":
      return "Session Context";
    case "learning_context":
      return "Learning Context";
    case "raw_source_fallback":
      return "Raw Source Fallback";
    default:
      return label;
  }
}

function summarizeAnswerBasis(answerBasis: string[]): {
  title: string;
  summary: string;
  stateLabel: string;
  emphasis: string;
  basisTags: string[];
} {
  const basisTags = answerBasis.map(formatAnswerBasisLabel);

  if (answerBasis.includes("formal_wiki")) {
    return {
      title: "공식 위키를 우선으로 정리한 응답",
      summary:
        answerBasis.length > 1
          ? "formal wiki를 중심으로 세션 맥락과 학습 상태를 함께 반영했습니다."
          : "현재 답변은 검증된 formal wiki를 기준으로 정리되었습니다.",
      stateLabel: "공식 지식 우선",
      emphasis: "검증된 공식 지식 층을 먼저 사용",
      basisTags,
    };
  }

  if (answerBasis.includes("raw_source_fallback")) {
    return {
      title: "raw source fallback으로 보강한 응답",
      summary: "검증된 wiki가 부족해 raw source를 보조 근거로 사용했습니다.",
      stateLabel: "보조 source 사용",
      emphasis: "fallback 경로가 사용됨",
      basisTags,
    };
  }

  if (answerBasis.includes("learning_context")) {
    return {
      title: "현재 학습 상태를 함께 반영한 응답",
      summary: "개인 learning note와 세션 맥락을 함께 읽어 설명했습니다.",
      stateLabel: "학습 맥락 반영",
      emphasis: "learning layer가 응답에 반영됨",
      basisTags,
    };
  }

  return {
    title: "세션 맥락 중심 응답",
    summary: "최근 세션과 현재 scope 안의 컨텍스트를 바탕으로 답변했습니다.",
    stateLabel: "세션 맥락",
    emphasis: "최근 대화 흐름을 우선 반영",
    basisTags,
  };
}

function formatRetrievalReason(reason: string): string {
  switch (reason) {
    case "high_relevance":
      return "질문과 가장 가까운 공식 위키 근거입니다.";
    case "recent_related_context":
      return "같은 맥락에서 이어진 최근 세션입니다.";
    case "fallback_match":
      return "검증된 위키가 부족해 raw source에서 보조 근거를 찾았습니다.";
    case "personal_learning_state":
      return "개인 learning state를 같이 반영했습니다.";
    default:
      return "현재 응답을 만드는 데 사용한 관련 근거입니다.";
  }
}

function formatSourceRef(sourceRef: QueryRetrievalRefApi["source_refs"][number]): string {
  const parts = [sourceRef.source_type, sourceRef.source_id, sourceRef.chunk_id].filter(Boolean);
  return parts.length ? parts.join(" · ") : "직접 근거 식별자 없음";
}

function buildEvidenceItem(
  ref: QueryRetrievalRefApi,
  contextId: string,
): AskEvidenceItem {
  const objectType =
    ref.entity_type === "wiki_page"
      ? "Wiki Page"
      : ref.entity_type === "raw_source"
        ? "Source"
        : ref.entity_type === "learning_note"
          ? "Learning Note"
          : "Session";
  const tone: AskEvidenceTone =
    ref.entity_type === "wiki_page"
      ? "grounded"
      : ref.entity_type === "raw_source"
        ? "fallback"
        : "supporting";
  const href =
    ref.entity_type === "wiki_page"
      ? appendContextToHref(`/wiki?page=${encodeURIComponent(ref.entity_id)}`, contextId)
      : ref.entity_type === "learning_note"
        ? appendContextToHref("/learning", contextId)
        : undefined;

  return {
    itemId: `${ref.entity_type}-${ref.entity_id}`,
    objectType,
    title:
      ref.entity_type === "wiki_page"
        ? "공식 위키 근거"
        : ref.entity_type === "raw_source"
          ? "Raw source 근거"
          : ref.entity_type === "learning_note"
            ? "Learning note 근거"
            : "세션 맥락 근거",
    summary: formatRetrievalReason(ref.reason),
    excerpt: ref.source_refs.length
      ? ref.source_refs.slice(0, 2).map(formatSourceRef).join(" / ")
      : `Entity ID · ${ref.entity_id}`,
    meta: `reason · ${ref.reason} · refs ${ref.source_refs.length}건`,
    tone,
    href,
  };
}

function formatRuntimeValue(value: unknown): string {
  if (typeof value === "boolean") {
    return value ? "예" : "아니오";
  }
  if (value == null || value === "") {
    return "없음";
  }
  return String(value);
}

function buildRuntimeDetails(runtime: QueryRuntimeMetaApi | null | undefined): Array<{ label: string; value: string }> {
  if (!runtime) {
    return [
      { label: "Runtime", value: "메타데이터 없음" },
      { label: "Stored answer", value: "기본 저장 응답" },
    ];
  }

  return [
    {
      label: "Answer source",
      value:
        runtime.answer_source === "llm_rewrite"
          ? "LLM rewrite"
          : runtime.answer_source === "deterministic_fallback"
            ? "Deterministic fallback"
            : formatRuntimeValue(runtime.answer_source),
    },
    {
      label: "Stored answer",
      value:
        runtime.stored_answer_source === "deterministic_fallback"
          ? "Deterministic fallback"
          : formatRuntimeValue(runtime.stored_answer_source),
    },
    {
      label: "LLM applied",
      value: formatRuntimeValue(runtime.llm_applied),
    },
    {
      label: "Model",
      value: runtime.configured_model ?? runtime.provider ?? "사용 안 함",
    },
  ];
}

function formatWritebackObjectType(kind: string): "Session" | "Learning Note" | "Candidate" {
  if (kind === "learning_note") {
    return "Learning Note";
  }
  if (kind === "candidate") {
    return "Candidate";
  }
  return "Session";
}

function formatWritebackStatus(status: string): string {
  switch (status) {
    case "registered":
      return "Registered";
    case "updated":
      return "Updated";
    case "open":
      return "Open";
    case "failed":
      return "Failed";
    default:
      return status;
  }
}

function buildLearningUpdate(
  writebackPlan: QueryWritebackPlanItemApi[],
  answerBasis: string[],
  contextId: string,
): AskPanelData["learningUpdate"] {
  const learningItem = writebackPlan.find((item) => item.kind === "learning_note");

  if (!learningItem) {
    return {
      title: "Learning Note unchanged",
      status: "No update",
      summary: "이번 질문은 learning layer를 새로 쓰지 않았습니다.",
      highlights: [
        "기존 learning note를 그대로 유지했습니다.",
        "질문 맥락은 session history에만 남았습니다.",
      ],
      nextActionLabel: "Learning 열기",
      nextActionHref: appendContextToHref("/learning", contextId),
    };
  }

  const highlights = [`Target · ${learningItem.target_id}`, `Status · ${formatWritebackStatus(learningItem.status)}`];
  if (answerBasis.includes("learning_context")) {
    highlights.push("현재 답변이 기존 learning context를 함께 참고했습니다.");
  }

  return {
    title: "Learning Note update",
    status: formatWritebackStatus(learningItem.status),
    summary: learningItem.explanation,
    highlights,
    nextActionLabel: "Learning에서 확인",
    nextActionHref: appendContextToHref("/learning", contextId),
  };
}

function buildCandidateOutcome(
  writebackPlan: QueryWritebackPlanItemApi[],
  contextId: string,
  role: KnowloopRole,
): AskPanelData["candidateOutcome"] {
  const candidateItem = writebackPlan.find((item) => item.kind === "candidate");
  const reviewAllowed = ["instructor", "operator", "validator"].includes(role);

  if (!candidateItem) {
    return {
      title: "Candidate not created",
      status: "No candidate",
      summary: "이번 질문은 별도 review 후보를 만들지 않았습니다.",
      targetLabel: "후보 없음",
      nextStep: reviewAllowed
        ? "필요한 경우 이후 질문에서 candidate가 생성되면 Review로 이어집니다."
        : "질문은 session과 learning layer에만 기록되었습니다.",
    };
  }

  return {
    title: candidateItem.action === "create" ? "Candidate created" : "Candidate updated",
    status: formatWritebackStatus(candidateItem.status),
    summary: candidateItem.explanation,
    targetLabel: `Candidate ID · ${candidateItem.target_id}`,
    nextStep: reviewAllowed
      ? "Review queue에서 승격, 병합, 드롭 여부를 바로 확인할 수 있습니다."
      : "이 후보는 review queue에 쌓이며, instructor 또는 validator가 후속 검토합니다.",
    href: reviewAllowed
      ? appendContextToHref(`/review?candidate=${encodeURIComponent(candidateItem.target_id)}`, contextId)
      : undefined,
  };
}

function buildWritebackTrail(writebackPlan: QueryWritebackPlanItemApi[]): AskPanelData["writebackTrail"] {
  return writebackPlan.map((item) => ({
    objectType: formatWritebackObjectType(item.kind),
    state: formatWritebackStatus(item.status),
    description: `${item.explanation} Target · ${item.target_id}`,
  }));
}

function splitAnswer(answer: string): {
  summary: string;
  detail: string | null;
} {
  const normalized = answer.trim();
  if (!normalized) {
    return { summary: "아직 응답이 없습니다.", detail: null };
  }

  const paragraphs = normalized.split(/\n\s*\n/g).map((part) => part.trim()).filter(Boolean);
  if (paragraphs.length <= 1) {
    return { summary: paragraphs[0] ?? normalized, detail: null };
  }

  return {
    summary: paragraphs[0],
    detail: paragraphs.slice(1).join("\n\n"),
  };
}

function summarizeCurrentAnswer(
  response: QueryResponseApi,
  runtime: QueryRuntimeMetaApi | null | undefined,
): Pick<AskConversationResult, "answerTitle" | "answerSummary" | "answerDetail" | "answerBadge"> {
  const { summary, detail } = splitAnswer(response.answer);
  const basisSummary = summarizeAnswerBasis(response.answer_basis);

  return {
    answerTitle: basisSummary.title,
    answerSummary: summary,
    answerDetail: detail,
    answerBadge:
      runtime?.answer_source === "llm_rewrite"
        ? "LLM rewrite"
        : runtime?.answer_source === "deterministic_fallback"
          ? "Deterministic fallback"
          : basisSummary.stateLabel,
  };
}

export function getAskResponseModeOptions(role: KnowloopRole): AskResponseModeOption[] {
  if (role === "validator") {
    return RESPONSE_MODE_OPTIONS.filter((option) => option.value === "review" || option.value === "concise");
  }

  if (role === "operator") {
    return RESPONSE_MODE_OPTIONS.filter((option) => option.value !== "teaching");
  }

  return RESPONSE_MODE_OPTIONS;
}

export function getAskPromptExamples(role: KnowloopRole): string[] {
  switch (role) {
    case "student":
      return [
        "연쇄법칙과 곱의 미분법이 언제 다른지 한 번 더 설명해줘.",
        "적분 치환법에서 u를 어떻게 골라야 할지 아직 헷갈려.",
        "이번 주 과제 제출 마감이 어디에 정리되어 있는지 알려줘.",
      ];
    case "instructor":
      return [
        "이번 반에서 chain rule 오개념이 반복되는 패턴을 정리해줘.",
        "과제 제출 FAQ로 승격할 만한 질문이 있는지 보고 싶어.",
        "다음 수업 도입에서 먼저 설명할 포인트를 요약해줘.",
      ];
    case "operator":
      return [
        "환불 정책을 학생 문의에 답할 수 있게 짧게 정리해줘.",
        "운영 공지에서 학생이 자주 묻는 질문을 찾아줘.",
      ];
    case "validator":
      return [
        "이 질문을 현재 wiki 기준으로 검토 관점에서 요약해줘.",
        "승격 전 검토가 필요한 근거가 충분한지 보고 싶어.",
      ];
    default:
      return [];
  }
}

export function extractAskTopics(sessionHistory: AskSessionHistoryItem[]): string[] {
  const counts = new Map<string, number>();
  for (const session of sessionHistory) {
    for (const tag of session.tags) {
      counts.set(tag, (counts.get(tag) ?? 0) + 1);
    }
  }

  return [...counts.entries()]
    .sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0], "ko-KR"))
    .slice(0, 6)
    .map(([tag]) => tag);
}

export async function fetchAskSessionHistory(
  context: AskFetchContext,
  options?: { query?: string; limit?: number },
): Promise<AskSessionHistoryItem[]> {
  const searchQuery = options?.query?.trim() ?? "";
  const limit = options?.limit ?? 12;
  const path = searchQuery
    ? `/api/v1/sessions/search?q=${encodeURIComponent(searchQuery)}&limit=${limit}`
    : `/api/v1/sessions/recent?limit=${limit}`;

  const envelope = await fetchEnvelope<SessionSearchHitApi[]>(path, {
    method: "GET",
    headers: buildHeaders(context, {
      requestId: buildRequestId(searchQuery ? "session-search" : "session-recent"),
    }),
  });

  return envelope.data.map(mapSessionHit);
}

export async function submitAskQuery(
  context: AskFetchContext,
  request: {
    message: string;
    responseMode: AskResponseMode;
    role: KnowloopRole;
    allowRawSourceFallback?: boolean;
  },
): Promise<AskConversationResult> {
  const envelope = await fetchEnvelope<QueryResponseApi>("/api/v1/query/respond", {
    method: "POST",
    headers: buildHeaders(context, {
      idempotencyKey: createAskMutationIdempotencyKey(),
      requestId: buildRequestId("query"),
    }),
    body: JSON.stringify({
      message: request.message,
      attachment_source_ids: [],
      allow_raw_source_fallback: request.allowRawSourceFallback ?? true,
      response_mode: request.responseMode,
    }),
  });

  const runtime = (envelope.meta?.runtime ?? null) as QueryRuntimeMetaApi | null;
  const response = envelope.data;
  const basisSummary = summarizeAnswerBasis(response.answer_basis);

  return {
    question: request.message,
    sessionId: response.session_id,
    createdAt: formatTimestamp(response.created_at),
    answer: response.answer,
    ...summarizeCurrentAnswer(response, runtime),
    panelData: {
      answerBasis: basisSummary,
      evidenceItems: response.retrieval_refs.map((item) => buildEvidenceItem(item, context.contextId)),
      runtimeDetails: buildRuntimeDetails(runtime),
      learningUpdate: buildLearningUpdate(response.writeback_plan, response.answer_basis, context.contextId),
      candidateOutcome: buildCandidateOutcome(response.writeback_plan, context.contextId, request.role),
      writebackTrail: buildWritebackTrail(response.writeback_plan),
    },
  };
}
