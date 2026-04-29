import type { BootstrapContextSelf, BootstrapContext } from "@/lib/context-bootstrap";
import { buildKnowloopContextHeaders, getDomainLabel, type KnowloopDomain } from "@/lib/workspace-context";

type ApiEnvelope<T> = {
  status: string;
  data: T;
  meta?: Record<string, unknown>;
};

type CandidateStatusApi = "open" | "promoted" | "merged" | "dropped";
type CandidateKindApi = "misconception" | "faq" | "intervention" | "unresolved_question" | "operations_note";
type ReviewDomainApi = "academic" | "operations" | "review";
type ReviewActionApi = "patch_preview" | "approve" | "merge" | "drop" | "resume_sync";
type WikiSyncStatusApi = "pending" | "synced";
type DropReasonApi = "insufficient_shared_value" | "obsolete_operations_signal" | "superseded_by_existing_candidate";

type CandidateSourceRefApi = {
  source_id: string;
  source_type: string;
  chunk_id?: string | null;
};

type ReviewCandidateApi = {
  candidate_id: string;
  kind: CandidateKindApi;
  status: CandidateStatusApi;
  title: string;
  summary: string;
  class_id: string;
  course_id: string;
  actor_role?: string;
  confidence: number;
  tags?: string[];
  source_refs: CandidateSourceRefApi[];
  session_refs?: string[];
  created_at: string;
  updated_at: string;
  approved_by?: string;
  approved_at?: string;
  merged_into?: string;
  related_page_id?: string;
  promotion_attempt_id?: string;
  wiki_sync_target_path?: string;
  approval_plan_fingerprint?: string;
  wiki_sync_status?: WikiSyncStatusApi;
  wiki_synced_at?: string;
  review_domain: ReviewDomainApi;
};

type ReviewAuditEventApi = {
  event_id: string;
  action: string;
  actor_role: string;
  actor_id: string;
  from_status?: string | null;
  to_status?: string | null;
  notes?: string | null;
  details?: Record<string, unknown> | null;
  request_id?: string | null;
  idempotency_key?: string | null;
  created_at: string;
};

type ReviewDetailApi = {
  candidate: ReviewCandidateApi;
  audit_events: ReviewAuditEventApi[];
  available_actions: ReviewActionApi[];
};

type ReviewPatchApi = {
  target_page_id?: string;
  target_path?: string;
  operation: "create" | "update" | "merge";
  title: string;
  summary: string;
  domain: string;
  course_id: string;
  class_id: string;
  actor_role?: string;
  change_plan?: string[];
  source_refs: CandidateSourceRefApi[];
  candidate_refs?: string[];
  created_at: string;
  approved_by?: string;
  approved_at?: string;
  approval_status?: "draft" | "approved" | "rejected";
};

type ReviewPatchPreviewApi = {
  candidate: ReviewCandidateApi;
  patch: ReviewPatchApi;
  before_markdown?: string | null;
  after_markdown: string;
};

type ReviewActionResponseApi = {
  candidate: ReviewCandidateApi;
  patch?: ReviewPatchApi | null;
  target_candidate?: ReviewCandidateApi | null;
  wiki_page?: Record<string, unknown> | null;
};

export type ReviewLifecycleLabel = "검토 대기" | "승격 완료" | "복구 필요" | "병합됨" | "드롭됨";
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
  action: ReviewActionApi;
  label: string;
  hint: string;
  tone: "primary" | "secondary" | "danger" | "warning";
};

export type ReviewCandidateSummary = {
  candidateId: string;
  title: string;
  kind: string;
  rawKind: CandidateKindApi;
  lifecycleState: ReviewLifecycleLabel;
  rawStatus: CandidateStatusApi;
  confidence: string;
  confidenceLabel: string;
  summary: string;
  queueNote: string;
  targetPage: string;
  targetPageId: string;
  targetPath: string;
  scopeLabel: string;
  updatedAt: string;
  sourceRefs: string[];
  sessionRefs: string[];
  reviewDomain: ReviewDomainApi;
  hasTargetHint: boolean;
};

export type ReviewCandidateDetail = ReviewCandidateSummary & {
  evidenceNote: string;
  auditEntries: ReviewAuditEntry[];
  availableActions: ReviewAction[];
  actionKeys: ReviewActionApi[];
};

export type ReviewPatchPreview = {
  patchPreviewTitle: string;
  patchPreviewSummary: string;
  targetPage: string;
  targetPath: string;
  operationLabel: string;
  patchLines: ReviewPatchLine[];
  changePlan: string[];
};

export type ReviewMutationResult = {
  candidate: ReviewCandidateSummary;
  summary: string;
};

export type ReviewActionDraft = {
  targetPageId: string;
  targetPath: string;
  notes: string;
  mergeTargetCandidateId: string;
  dropReason: DropReasonApi;
};

type ReviewFetchContext = {
  contextId: string;
};

const REVIEW_STATUS_ORDER: CandidateStatusApi[] = ["open", "promoted", "merged", "dropped"];
const DROP_REASON_OPTIONS: DropReasonApi[] = [
  "insufficient_shared_value",
  "superseded_by_existing_candidate",
  "obsolete_operations_signal",
];

function buildHeaders(context: ReviewFetchContext, options?: { idempotencyKey?: string; requestId?: string }): HeadersInit {
  return {
    Accept: "application/json",
    "Content-Type": "application/json",
    ...buildKnowloopContextHeaders(context.contextId),
    "X-Request-Id": options?.requestId ?? buildRequestId("review"),
    ...(options?.idempotencyKey ? { "Idempotency-Key": options.idempotencyKey } : {}),
  };
}

function buildRequestId(prefix: string): string {
  const suffix = typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID().slice(0, 8) : `${Date.now()}`;
  return `web-${prefix}-${suffix}`;
}

function buildIdempotencyKey(prefix: string, candidateId: string): string {
  const suffix = typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `web-${prefix}-${candidateId}-${suffix}`;
}

export function createReviewMutationIdempotencyKey(action: "approve" | "merge" | "drop" | "resume_sync", candidateId: string): string {
  return buildIdempotencyKey(action === "resume_sync" ? "resume-sync" : action, candidateId);
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

function formatReviewKind(kind: CandidateKindApi): string {
  switch (kind) {
    case "faq":
      return "FAQ";
    case "misconception":
      return "오개념";
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

function formatConfidenceLabel(confidence: number): string {
  if (confidence >= 0.9) {
    return "매우 높음";
  }
  if (confidence >= 0.8) {
    return "높음";
  }
  if (confidence >= 0.65) {
    return "보통";
  }
  return "낮음";
}

function formatLifecycleState(candidate: ReviewCandidateApi): ReviewLifecycleLabel {
  if (candidate.status === "promoted" && candidate.wiki_sync_status === "pending") {
    return "복구 필요";
  }

  switch (candidate.status) {
    case "open":
      return "검토 대기";
    case "promoted":
      return "승격 완료";
    case "merged":
      return "병합됨";
    case "dropped":
      return "드롭됨";
    default:
      return "검토 대기";
  }
}

function resolveScopeLabel(
  reviewDomain: ReviewDomainApi,
  self: BootstrapContextSelf | null,
  activeContext: BootstrapContext | null,
  courseId: string,
  classId: string,
): string {
  const courseLabel = self?.courseId === courseId ? self.courseLabel : activeContext?.courseId === courseId ? activeContext.courseLabel : courseId;
  const classLabel = self?.classId === classId ? self.classLabel : activeContext?.classId === classId ? activeContext.classLabel : classId;
  const domainLabel = getDomainLabel(reviewDomain as KnowloopDomain);

  return [courseLabel, classLabel, domainLabel].filter(Boolean).join(" · ");
}

function resolveTargetLabel(candidate: ReviewCandidateApi): { page: string; path: string; hasTargetHint: boolean } {
  const targetPage = candidate.related_page_id ?? "대상 페이지 지정 필요";
  const targetPath = candidate.wiki_sync_target_path ?? "경로 힌트 없음";
  return {
    page: targetPage,
    path: targetPath,
    hasTargetHint: Boolean(candidate.related_page_id || candidate.wiki_sync_target_path),
  };
}

function resolveQueueNote(candidate: ReviewCandidateApi): string {
  if (candidate.status === "promoted" && candidate.wiki_sync_status === "pending") {
    return "resume-sync 필요";
  }
  if (candidate.status === "promoted") {
    return "공식 위키 반영 완료";
  }
  if (candidate.status === "merged") {
    return "다른 후보에 병합됨";
  }
  if (candidate.status === "dropped") {
    return "검토 종료";
  }
  if (candidate.review_domain === "operations") {
    return "운영 지식 검토 대기";
  }
  return "학습 지식 검토 대기";
}

function formatSourceRef(ref: CandidateSourceRefApi): string {
  return ref.chunk_id ? `${ref.source_id} · ${ref.chunk_id}` : ref.source_id;
}

function summarizeEvidence(candidate: ReviewCandidateApi): string {
  const sourceCount = candidate.source_refs.length;
  const sessionCount = candidate.session_refs?.length ?? 0;
  return `${formatReviewKind(candidate.kind)} 후보이며 source ${sourceCount}개와 session ${sessionCount}건이 근거로 연결되어 있습니다. 현재 summary는 공식 위키 반영 전 reviewer가 읽는 운영 요약입니다.`;
}

function humanizeAuditAction(action: string): string {
  switch (action) {
    case "candidate_created":
      return "candidate_created";
    case "candidate_promoted":
      return "candidate_promoted";
    case "candidate_dropped":
      return "candidate_dropped";
    case "candidate_merged":
      return "candidate_merged";
    case "candidate_wiki_sync_pending":
      return "candidate_wiki_sync_pending";
    case "candidate_wiki_synced":
      return "candidate_wiki_synced";
    case "candidate_wiki_sync_resumed":
      return "candidate_wiki_sync_resumed";
    default:
      return action;
  }
}

function summarizeAuditEvent(event: ReviewAuditEventApi): string {
  if (event.notes) {
    return event.notes;
  }
  if (event.from_status || event.to_status) {
    return `상태 전이: ${event.from_status ?? "-"} -> ${event.to_status ?? "-"}`;
  }
  if (event.request_id) {
    return `request ${event.request_id}에서 ${event.action}가 기록되었습니다.`;
  }
  return "세부 노트 없이 기록된 review 이벤트입니다.";
}

function mapAuditEntry(event: ReviewAuditEventApi): ReviewAuditEntry {
  return {
    entryId: event.event_id,
    label: humanizeAuditAction(event.action),
    actor: `${event.actor_role} · ${event.actor_id}`,
    createdAt: formatTimestamp(event.created_at),
    summary: summarizeAuditEvent(event),
  };
}

function mapReviewAction(action: ReviewActionApi): ReviewAction {
  switch (action) {
    case "patch_preview":
      return {
        action,
        label: "Patch preview",
        hint: "공식 위키에 어떤 지식 변화가 생기는지 먼저 확인합니다.",
        tone: "secondary",
      };
    case "approve":
      return {
        action,
        label: "Approve",
        hint: "이 candidate를 공식 위키 승격 대상으로 확정합니다.",
        tone: "primary",
      };
    case "merge":
      return {
        action,
        label: "Merge",
        hint: "중복 후보를 더 강한 canonical candidate로 병합합니다.",
        tone: "secondary",
      };
    case "drop":
      return {
        action,
        label: "Drop",
        hint: "근거가 부족하거나 이미 대체된 후보를 종료합니다.",
        tone: "danger",
      };
    case "resume_sync":
      return {
        action,
        label: "Resume sync",
        hint: "멈춘 wiki sync를 이어서 공식 위키 반영을 마무리합니다.",
        tone: "warning",
      };
    default:
      return {
        action,
        label: action,
        hint: "Review workflow action",
        tone: "secondary",
      };
  }
}

function mapCandidateSummary(candidate: ReviewCandidateApi, self: BootstrapContextSelf | null, activeContext: BootstrapContext | null): ReviewCandidateSummary {
  const target = resolveTargetLabel(candidate);
  return {
    candidateId: candidate.candidate_id,
    title: candidate.title,
    kind: formatReviewKind(candidate.kind),
    rawKind: candidate.kind,
    lifecycleState: formatLifecycleState(candidate),
    rawStatus: candidate.status,
    confidence: candidate.confidence.toFixed(2),
    confidenceLabel: formatConfidenceLabel(candidate.confidence),
    summary: candidate.summary,
    queueNote: resolveQueueNote(candidate),
    targetPage: target.page,
    targetPageId: candidate.related_page_id ?? "",
    targetPath: candidate.wiki_sync_target_path ?? "",
    scopeLabel: resolveScopeLabel(candidate.review_domain, self, activeContext, candidate.course_id, candidate.class_id),
    updatedAt: formatTimestamp(candidate.updated_at),
    sourceRefs: candidate.source_refs.map(formatSourceRef),
    sessionRefs: candidate.session_refs ?? [],
    reviewDomain: candidate.review_domain,
    hasTargetHint: target.hasTargetHint,
  };
}

function mapCandidateDetail(detail: ReviewDetailApi, self: BootstrapContextSelf | null, activeContext: BootstrapContext | null): ReviewCandidateDetail {
  const summary = mapCandidateSummary(detail.candidate, self, activeContext);
  return {
    ...summary,
    evidenceNote: summarizeEvidence(detail.candidate),
    auditEntries: detail.audit_events.map(mapAuditEntry),
    availableActions: detail.available_actions.map(mapReviewAction),
    actionKeys: detail.available_actions,
  };
}

function stripFrontmatter(markdown: string | null | undefined): string[] {
  if (!markdown) {
    return [];
  }
  const normalized = markdown.replace(/\r/g, "");
  if (!normalized.startsWith("---\n")) {
    return normalized.split("\n");
  }
  const closingIndex = normalized.indexOf("\n---\n", 4);
  const body = closingIndex >= 0 ? normalized.slice(closingIndex + 5) : normalized;
  return body.split("\n");
}

function buildPatchLines(beforeMarkdown: string | null | undefined, afterMarkdown: string): ReviewPatchLine[] {
  const beforeLines = stripFrontmatter(beforeMarkdown);
  const afterLines = stripFrontmatter(afterMarkdown);
  const lines: ReviewPatchLine[] = [];

  const matrix = Array.from({ length: beforeLines.length + 1 }, () => Array<number>(afterLines.length + 1).fill(0));
  for (let leftIndex = beforeLines.length - 1; leftIndex >= 0; leftIndex -= 1) {
    for (let rightIndex = afterLines.length - 1; rightIndex >= 0; rightIndex -= 1) {
      matrix[leftIndex][rightIndex] =
        beforeLines[leftIndex] === afterLines[rightIndex]
          ? matrix[leftIndex + 1][rightIndex + 1] + 1
          : Math.max(matrix[leftIndex + 1][rightIndex], matrix[leftIndex][rightIndex + 1]);
    }
  }

  let leftIndex = 0;
  let rightIndex = 0;
  while (leftIndex < beforeLines.length && rightIndex < afterLines.length) {
    if (beforeLines[leftIndex] === afterLines[rightIndex]) {
      lines.push({
        lineId: `ctx-${leftIndex}-${rightIndex}`,
        kind: "context",
        text: beforeLines[leftIndex],
      });
      leftIndex += 1;
      rightIndex += 1;
      continue;
    }

    if (matrix[leftIndex + 1][rightIndex] >= matrix[leftIndex][rightIndex + 1]) {
      lines.push({
        lineId: `rem-${leftIndex}`,
        kind: "removal",
        text: beforeLines[leftIndex],
      });
      leftIndex += 1;
      continue;
    }

    lines.push({
      lineId: `add-${rightIndex}`,
      kind: "addition",
      text: afterLines[rightIndex],
    });
    rightIndex += 1;
  }

  while (leftIndex < beforeLines.length) {
    lines.push({
      lineId: `rem-tail-${leftIndex}`,
      kind: "removal",
      text: beforeLines[leftIndex],
    });
    leftIndex += 1;
  }

  while (rightIndex < afterLines.length) {
    lines.push({
      lineId: `add-tail-${rightIndex}`,
      kind: "addition",
      text: afterLines[rightIndex],
    });
    rightIndex += 1;
  }

  if (!lines.length) {
    lines.push({ lineId: "ctx-empty", kind: "context", text: "구조 변화는 없지만 메타데이터 또는 상태 정보가 갱신됩니다." });
  }

  return lines;
}

function summarizePatch(patch: ReviewPatchApi): string {
  if (patch.change_plan?.length) {
    return patch.change_plan.join(" · ");
  }
  return `${patch.title} 문서를 ${patch.operation} 방식으로 갱신하는 review patch입니다.`;
}

function mapPatchPreview(preview: ReviewPatchPreviewApi): ReviewPatchPreview {
  return {
    patchPreviewTitle: `${preview.patch.title} patch preview`,
    patchPreviewSummary: summarizePatch(preview.patch),
    targetPage: preview.patch.target_page_id ?? preview.candidate.related_page_id ?? "대상 페이지 지정 필요",
    targetPath: preview.patch.target_path ?? preview.candidate.wiki_sync_target_path ?? "경로 힌트 없음",
    operationLabel: preview.patch.operation,
    patchLines: buildPatchLines(preview.before_markdown, preview.after_markdown),
    changePlan: preview.patch.change_plan ?? [],
  };
}

async function fetchEnvelope<T>(path: string, init?: RequestInit): Promise<ApiEnvelope<T>> {
  const response = await fetch(path, {
    ...init,
    cache: "no-store",
  });

  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as
      | { error?: { code?: string; message?: string } }
      | null;
    throw new Error(payload?.error?.message ?? payload?.error?.code ?? `Review request failed with ${response.status}.`);
  }

  return (await response.json()) as ApiEnvelope<T>;
}

async function fetchCandidatesByStatus(
  context: ReviewFetchContext,
  status: CandidateStatusApi,
  self: BootstrapContextSelf | null,
  activeContext: BootstrapContext | null,
): Promise<Array<{ candidate: ReviewCandidateSummary; updatedAtValue: string }>> {
  const limit = 100;
  let offset = 0;
  let total = Number.POSITIVE_INFINITY;
  const entries: Array<{ candidate: ReviewCandidateSummary; updatedAtValue: string }> = [];

  while (offset < total) {
    const searchParams = new URLSearchParams({
      status,
      limit: String(limit),
      offset: String(offset),
    });
    const envelope = await fetchEnvelope<ReviewCandidateApi[]>(`/api/v1/review/candidates?${searchParams.toString()}`, {
      headers: buildHeaders(context, { requestId: buildRequestId(`review-list-${status}`) }),
    });

    entries.push(
      ...envelope.data.map((candidate) => ({
        candidate: mapCandidateSummary(candidate, self, activeContext),
        updatedAtValue: candidate.updated_at,
      })),
    );

    total = Number(envelope.meta?.total ?? entries.length);
    if (!envelope.data.length) {
      break;
    }
    offset += envelope.data.length;
  }

  return entries;
}

export async function fetchReviewCandidateList(
  context: ReviewFetchContext,
  self: BootstrapContextSelf | null,
  activeContext: BootstrapContext | null,
): Promise<ReviewCandidateSummary[]> {
  const groups = await Promise.all(REVIEW_STATUS_ORDER.map((status) => fetchCandidatesByStatus(context, status, self, activeContext)));
  const deduped = new Map<string, { candidate: ReviewCandidateSummary; updatedAtValue: string }>();
  groups.flat().forEach((entry) => {
    deduped.set(entry.candidate.candidateId, entry);
  });

  return Array.from(deduped.values())
    .sort((left, right) => Date.parse(right.updatedAtValue) - Date.parse(left.updatedAtValue))
    .map((entry) => entry.candidate);
}

export async function fetchReviewCandidateDetail(
  context: ReviewFetchContext,
  candidateId: string,
  self: BootstrapContextSelf | null,
  activeContext: BootstrapContext | null,
): Promise<ReviewCandidateDetail> {
  const envelope = await fetchEnvelope<ReviewDetailApi>(`/api/v1/review/candidates/${candidateId}`, {
    headers: buildHeaders(context, { requestId: buildRequestId("review-detail") }),
  });

  return mapCandidateDetail(envelope.data, self, activeContext);
}

export async function fetchReviewPatchPreview(
  context: ReviewFetchContext,
  candidateId: string,
  payload: { targetPageId?: string; targetPath?: string; notes?: string },
): Promise<ReviewPatchPreview> {
  const requestBody: Record<string, string> = {};
  if (payload.targetPageId?.trim()) {
    requestBody.target_page_id = payload.targetPageId.trim();
  }
  if (payload.targetPath?.trim()) {
    requestBody.target_path = payload.targetPath.trim();
  }
  if (payload.notes?.trim()) {
    requestBody.notes = payload.notes.trim();
  }

  const envelope = await fetchEnvelope<ReviewPatchPreviewApi>(`/api/v1/review/candidates/${candidateId}/patch-preview`, {
    method: "POST",
    headers: buildHeaders(context, { requestId: buildRequestId("review-preview") }),
    body: JSON.stringify(requestBody),
  });

  return mapPatchPreview(envelope.data);
}

async function postReviewMutation(
  context: ReviewFetchContext,
  candidateId: string,
  route: "approve" | "merge" | "drop" | "resume-sync",
  payload: Record<string, string>,
  idempotencyKey: string,
): Promise<ReviewActionResponseApi> {
  const envelope = await fetchEnvelope<ReviewActionResponseApi>(`/api/v1/review/candidates/${candidateId}/${route}`, {
    method: "POST",
    headers: buildHeaders(context, {
      requestId: buildRequestId(route),
      idempotencyKey,
    }),
    body: JSON.stringify(payload),
  });

  return envelope.data;
}

export async function approveReviewCandidate(
  context: ReviewFetchContext,
  candidateId: string,
  payload: { targetPageId?: string; targetPath?: string; notes?: string },
  idempotencyKey: string,
  self: BootstrapContextSelf | null,
  activeContext: BootstrapContext | null,
): Promise<ReviewMutationResult> {
  const response = await postReviewMutation(context, candidateId, "approve", {
    ...(payload.targetPageId?.trim() ? { target_page_id: payload.targetPageId.trim() } : {}),
    ...(payload.targetPath?.trim() ? { target_path: payload.targetPath.trim() } : {}),
    ...(payload.notes?.trim() ? { approval_notes: payload.notes.trim() } : {}),
  }, idempotencyKey);
  return {
    candidate: mapCandidateSummary(response.candidate, self, activeContext),
    summary: "candidate가 공식 위키 승격 흐름으로 이동했습니다.",
  };
}

export async function mergeReviewCandidate(
  context: ReviewFetchContext,
  candidateId: string,
  payload: { targetCandidateId: string; notes?: string },
  idempotencyKey: string,
  self: BootstrapContextSelf | null,
  activeContext: BootstrapContext | null,
): Promise<ReviewMutationResult> {
  const response = await postReviewMutation(context, candidateId, "merge", {
    target_candidate_id: payload.targetCandidateId,
    ...(payload.notes?.trim() ? { merge_notes: payload.notes.trim() } : {}),
  }, idempotencyKey);
  return {
    candidate: mapCandidateSummary(response.candidate, self, activeContext),
    summary: "candidate가 다른 canonical 후보로 병합되었습니다.",
  };
}

export async function dropReviewCandidate(
  context: ReviewFetchContext,
  candidateId: string,
  payload: { reason: DropReasonApi; notes?: string },
  idempotencyKey: string,
  self: BootstrapContextSelf | null,
  activeContext: BootstrapContext | null,
): Promise<ReviewMutationResult> {
  const response = await postReviewMutation(context, candidateId, "drop", {
    reason: payload.reason,
    ...(payload.notes?.trim() ? { drop_notes: payload.notes.trim() } : {}),
  }, idempotencyKey);
  return {
    candidate: mapCandidateSummary(response.candidate, self, activeContext),
    summary: "candidate가 review workflow에서 종료되었습니다.",
  };
}

export async function resumeReviewCandidateSync(
  context: ReviewFetchContext,
  candidateId: string,
  payload: { notes?: string },
  idempotencyKey: string,
  self: BootstrapContextSelf | null,
  activeContext: BootstrapContext | null,
): Promise<ReviewMutationResult> {
  const response = await postReviewMutation(context, candidateId, "resume-sync", {
    ...(payload.notes?.trim() ? { resume_notes: payload.notes.trim() } : {}),
  }, idempotencyKey);
  return {
    candidate: mapCandidateSummary(response.candidate, self, activeContext),
    summary: "중단된 wiki sync 재개를 요청했습니다.",
  };
}

export function createDefaultReviewActionDraft(candidate: ReviewCandidateSummary, mergeOptions: ReviewCandidateSummary[]): ReviewActionDraft {
  const defaultDropReason: DropReasonApi =
    candidate.rawKind === "operations_note"
      ? "obsolete_operations_signal"
      : candidate.rawKind === "unresolved_question"
        ? "insufficient_shared_value"
        : "superseded_by_existing_candidate";

  return {
    targetPageId: candidate.targetPageId,
    targetPath: candidate.targetPath,
    notes: "",
    mergeTargetCandidateId: mergeOptions[0]?.candidateId ?? "",
    dropReason: defaultDropReason,
  };
}

export function getDropReasonLabel(reason: DropReasonApi): string {
  switch (reason) {
    case "insufficient_shared_value":
      return "공유 가치 부족";
    case "obsolete_operations_signal":
      return "운영 신호 만료";
    case "superseded_by_existing_candidate":
      return "기존 후보로 대체됨";
    default:
      return reason;
  }
}

export function getDropReasonOptions(): DropReasonApi[] {
  return DROP_REASON_OPTIONS;
}
