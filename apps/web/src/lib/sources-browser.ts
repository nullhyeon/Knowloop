import type { BootstrapContextSelf, BootstrapProfile } from "@/lib/context-bootstrap";
import { getDomainLabel, type KnowloopDomain, type KnowloopRole } from "@/lib/demo-data";
import { fetchWikiPageDetail, fetchWikiPageList } from "@/lib/wiki-browser";

type ApiEnvelope<T> = {
  status: string;
  data: T;
  meta?: Record<string, unknown>;
};

type SourceTypeApi =
  | "lecture_note"
  | "lecture_transcript"
  | "student_question"
  | "assignment_feedback"
  | "announcement"
  | "operations_note"
  | "counseling_note";

type SourceDomainApi = "academic" | "operations";
type SourceStatusApi = "registered";
type SourceActorRoleApi = KnowloopRole | "system";
type ReviewCandidateStatusApi = "open" | "promoted" | "merged" | "dropped";
type ReviewCandidateKindApi = "misconception" | "faq" | "intervention" | "unresolved_question" | "operations_note";
type WikiSyncStatusApi = "pending" | "synced";

type SourceRecordApi = {
  source_id: string;
  source_type: SourceTypeApi;
  domain: SourceDomainApi;
  title: string;
  class_id: string;
  course_id: string;
  actor_role: SourceActorRoleApi;
  status: SourceStatusApi;
  stored_path: string;
  origin_path: string;
  checksum: string;
  created_at: string;
  uploaded_by: string | null;
  mime_type: string | null;
  filename: string | null;
  tags: string[];
  summary: string | null;
};

type ReviewCandidateSourceRefApi = {
  source_id: string;
  source_type: string;
  chunk_id?: string | null;
};

type ReviewCandidateListApi = {
  candidate_id: string;
  kind: ReviewCandidateKindApi;
  status: ReviewCandidateStatusApi;
  title: string;
  summary: string;
  review_domain: "academic" | "operations" | "review";
  source_refs: ReviewCandidateSourceRefApi[];
  wiki_sync_status?: WikiSyncStatusApi;
};

type SourceFetchContext = {
  profileId: string;
};

type SourceTraceabilityIndex = {
  wikiBySourceId: Record<string, SourceTraceabilityWikiLink[]>;
  candidateBySourceId: Record<string, SourceTraceabilityCandidateLink[]>;
};

export type SourceStatusLabel = "Registered" | "Needs Sync" | "Active";

export type SourceTypeOption = {
  value: SourceTypeApi;
  label: string;
  hint: string;
};

export type SourceTraceabilityWikiLink = {
  pageId: string;
  title: string;
};

export type SourceTraceabilityCandidateLink = {
  candidateId: string;
  title: string;
  kindLabel: string;
  lifecycleState: string;
};

export type SourceBrowserRecord = {
  sourceId: string;
  title: string;
  sourceType: SourceTypeApi;
  sourceTypeLabel: string;
  domain: SourceDomainApi;
  domainLabel: string;
  scopeLabel: string;
  statusLabel: SourceStatusLabel;
  registeredAt: string;
  ownerLabel: string;
  summary: string;
  linkedWikiPages: SourceTraceabilityWikiLink[];
  linkedCandidates: SourceTraceabilityCandidateLink[];
  originLabel: string;
  storedPath: string;
  filename: string | null;
  mimeType: string | null;
  tags: string[];
  canRegister: boolean;
};

export type SourceRegistrationDraft = {
  sourceType: SourceTypeApi;
  title: string;
  content: string;
  filename: string;
  mimeType: string;
  tags: string;
};

const SOURCE_TYPE_OPTIONS: Record<SourceTypeApi, SourceTypeOption> = {
  lecture_note: {
    value: "lecture_note",
    label: "강의 노트",
    hint: "수업 자료나 판서 요약처럼 공식 개념 설명의 근거가 되는 자료",
  },
  lecture_transcript: {
    value: "lecture_transcript",
    label: "강의 전사",
    hint: "수업 발화 기록이나 정리본처럼 설명 흐름을 남기는 자료",
  },
  student_question: {
    value: "student_question",
    label: "학생 질문",
    hint: "반복 질문 패턴과 candidate 근거로 이어질 수 있는 raw 질문 자료",
  },
  assignment_feedback: {
    value: "assignment_feedback",
    label: "과제 피드백",
    hint: "채점 피드백이나 자주 틀리는 포인트를 남기는 자료",
  },
  announcement: {
    value: "announcement",
    label: "공지",
    hint: "수업/운영 공지처럼 FAQ나 운영 위키로 연결되는 자료",
  },
  operations_note: {
    value: "operations_note",
    label: "운영 메모",
    hint: "등록/환불/출결 등 운영 정책과 연결되는 내부 메모",
  },
  counseling_note: {
    value: "counseling_note",
    label: "상담 메모",
    hint: "학생 상담이나 지원 이슈를 다루는 운영 자료",
  },
};

const REVIEW_STATUS_ORDER: ReviewCandidateStatusApi[] = ["open", "promoted", "merged", "dropped"];

function buildHeaders(context: SourceFetchContext, options?: { idempotencyKey?: string; requestId?: string }): HeadersInit {
  return {
    Accept: "application/json",
    "Content-Type": "application/json",
    "X-Knowloop-Profile-Id": context.profileId,
    "X-Request-Id": options?.requestId ?? buildRequestId("sources"),
    ...(options?.idempotencyKey ? { "Idempotency-Key": options.idempotencyKey } : {}),
  };
}

function buildRequestId(prefix: string): string {
  const suffix = typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID().slice(0, 8) : `${Date.now()}`;
  return `web-${prefix}-${suffix}`;
}

export function createSourceRegistrationIdempotencyKey(): string {
  const suffix = typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `web-source-register-${suffix}`;
}

export function buildSourceRegistrationFingerprint(draft: SourceRegistrationDraft): string {
  const payload = {
    sourceType: draft.sourceType,
    title: draft.title.trim(),
    content: draft.content,
    filename: draft.filename.trim(),
    mimeType: draft.mimeType.trim(),
    tags: normalizeTagInput(draft.tags),
  };
  return JSON.stringify(payload);
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
    throw new Error(payload?.error?.message ?? payload?.error?.code ?? `Sources request failed with ${response.status}.`);
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

function resolveScopeLabel(
  domain: SourceDomainApi,
  self: BootstrapContextSelf | null,
  activeProfile: BootstrapProfile | null,
  courseId: string,
  classId: string,
): string {
  const courseLabel = self?.courseId === courseId ? self.courseLabel : activeProfile?.courseId === courseId ? activeProfile.courseLabel : courseId;
  const classLabel = self?.classId === classId ? self.classLabel : activeProfile?.classId === classId ? activeProfile.classLabel : classId;
  const domainLabel = getDomainLabel(domain as KnowloopDomain);
  return [courseLabel, classLabel, domainLabel].filter(Boolean).join(" · ");
}

function getSourceTypeOption(sourceType: SourceTypeApi): SourceTypeOption {
  return SOURCE_TYPE_OPTIONS[sourceType];
}

function formatOwnerLabel(source: SourceRecordApi): string {
  if (source.uploaded_by?.trim()) {
    return source.uploaded_by;
  }

  switch (source.actor_role) {
    case "instructor":
      return "강사 업로드";
    case "operator":
      return "운영 업로드";
    case "validator":
      return "검토자 업로드";
    case "student":
      return "학생 업로드";
    case "system":
      return "시스템 등록";
    default:
      return source.actor_role;
  }
}

function resolveOriginLabel(source: SourceRecordApi): string {
  if (source.filename?.trim()) {
    return source.filename.trim();
  }
  return source.stored_path;
}

function resolveLifecycleLabel(candidate: ReviewCandidateListApi): string {
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
      return candidate.status;
  }
}

function formatCandidateKind(kind: ReviewCandidateKindApi): string {
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

function summarizeSource(source: SourceRecordApi, traceability: SourceTraceabilityIndex): string {
  if (source.summary?.trim()) {
    return source.summary.trim();
  }

  const wikiCount = traceability.wikiBySourceId[source.source_id]?.length ?? 0;
  const candidateCount = traceability.candidateBySourceId[source.source_id]?.length ?? 0;
  if (wikiCount || candidateCount) {
    return `${getSourceTypeOption(source.source_type).label} 자료이며 현재 ${wikiCount}개 wiki, ${candidateCount}개 candidate와 연결되어 있습니다.`;
  }

  return `${getSourceTypeOption(source.source_type).label} raw source로 등록되었고, 아직 직접 연결된 wiki 또는 candidate는 없습니다.`;
}

function resolveStatusLabel(source: SourceRecordApi, traceability: SourceTraceabilityIndex): SourceStatusLabel {
  const wikiCount = traceability.wikiBySourceId[source.source_id]?.length ?? 0;
  const candidateCount = traceability.candidateBySourceId[source.source_id]?.length ?? 0;
  if (wikiCount > 0) {
    return "Active";
  }
  if (candidateCount > 0) {
    return "Needs Sync";
  }
  return source.status === "registered" ? "Registered" : "Registered";
}

function mapSourceRecord(
  source: SourceRecordApi,
  self: BootstrapContextSelf | null,
  activeProfile: BootstrapProfile | null,
  traceability: SourceTraceabilityIndex,
): SourceBrowserRecord {
  return {
    sourceId: source.source_id,
    title: source.title,
    sourceType: source.source_type,
    sourceTypeLabel: getSourceTypeOption(source.source_type).label,
    domain: source.domain,
    domainLabel: getDomainLabel(source.domain as KnowloopDomain),
    scopeLabel: resolveScopeLabel(source.domain, self, activeProfile, source.course_id, source.class_id),
    statusLabel: resolveStatusLabel(source, traceability),
    registeredAt: formatTimestamp(source.created_at),
    ownerLabel: formatOwnerLabel(source),
    summary: summarizeSource(source, traceability),
    linkedWikiPages: traceability.wikiBySourceId[source.source_id] ?? [],
    linkedCandidates: traceability.candidateBySourceId[source.source_id] ?? [],
    originLabel: resolveOriginLabel(source),
    storedPath: source.stored_path,
    filename: source.filename,
    mimeType: source.mime_type,
    tags: source.tags,
    canRegister: activeProfile?.role === "instructor" || activeProfile?.role === "operator",
  };
}

async function fetchAllSourceRecords(context: SourceFetchContext): Promise<SourceRecordApi[]> {
  const limit = 100;
  let offset = 0;
  let total = Number.POSITIVE_INFINITY;
  const sources: SourceRecordApi[] = [];

  while (offset < total) {
    const searchParams = new URLSearchParams({
      limit: String(limit),
      offset: String(offset),
    });
    const envelope = await fetchEnvelope<SourceRecordApi[]>(`/api/v1/sources?${searchParams.toString()}`, {
      headers: buildHeaders(context, { requestId: buildRequestId("sources-list") }),
    });
    sources.push(...envelope.data);
    total = Number(envelope.meta?.total ?? sources.length);
    if (!envelope.data.length) {
      break;
    }
    offset += envelope.data.length;
  }

  return sources;
}

async function fetchReviewCandidatesByStatus(context: SourceFetchContext, status: ReviewCandidateStatusApi): Promise<ReviewCandidateListApi[]> {
  const limit = 100;
  let offset = 0;
  let total = Number.POSITIVE_INFINITY;
  const candidates: ReviewCandidateListApi[] = [];

  while (offset < total) {
    const searchParams = new URLSearchParams({
      status,
      limit: String(limit),
      offset: String(offset),
    });
    const envelope = await fetchEnvelope<ReviewCandidateListApi[]>(`/api/v1/review/candidates?${searchParams.toString()}`, {
      headers: buildHeaders(context, { requestId: buildRequestId(`sources-review-${status}`) }),
    });
    candidates.push(...envelope.data);
    total = Number(envelope.meta?.total ?? candidates.length);
    if (!envelope.data.length) {
      break;
    }
    offset += envelope.data.length;
  }

  return candidates;
}

export async function fetchSourceTraceability(
  context: SourceFetchContext,
  self: BootstrapContextSelf | null,
  activeProfile: BootstrapProfile | null,
): Promise<SourceTraceabilityIndex> {
  const [candidateGroups, wikiPages] = await Promise.all([
    Promise.all(REVIEW_STATUS_ORDER.map((status) => fetchReviewCandidatesByStatus(context, status))),
    fetchWikiPageList(context, "", self, activeProfile),
  ]);

  const wikiDetails = await Promise.all(
    wikiPages.map((page) => fetchWikiPageDetail(context, page.pageId, self, activeProfile)),
  );

  const wikiBySourceId: Record<string, SourceTraceabilityWikiLink[]> = {};
  for (const page of wikiDetails) {
    for (const sourceId of page.sourceRefs) {
      wikiBySourceId[sourceId] = [...(wikiBySourceId[sourceId] ?? []), { pageId: page.pageId, title: page.title }];
    }
  }

  const candidateBySourceId: Record<string, SourceTraceabilityCandidateLink[]> = {};
  for (const candidate of candidateGroups.flat()) {
    for (const ref of candidate.source_refs) {
      candidateBySourceId[ref.source_id] = [
        ...(candidateBySourceId[ref.source_id] ?? []),
        {
          candidateId: candidate.candidate_id,
          title: candidate.title,
          kindLabel: formatCandidateKind(candidate.kind),
          lifecycleState: resolveLifecycleLabel(candidate),
        },
      ];
    }
  }

  return {
    wikiBySourceId,
    candidateBySourceId,
  };
}

export async function fetchSourceCatalog(
  context: SourceFetchContext,
  self: BootstrapContextSelf | null,
  activeProfile: BootstrapProfile | null,
  traceability: SourceTraceabilityIndex,
): Promise<SourceBrowserRecord[]> {
  const sources = await fetchAllSourceRecords(context);
  return sources.map((source) => mapSourceRecord(source, self, activeProfile, traceability));
}

export async function fetchSourceDetail(
  context: SourceFetchContext,
  sourceId: string,
  self: BootstrapContextSelf | null,
  activeProfile: BootstrapProfile | null,
  traceability: SourceTraceabilityIndex,
): Promise<SourceBrowserRecord> {
  const envelope = await fetchEnvelope<SourceRecordApi>(`/api/v1/sources/${sourceId}`, {
    headers: buildHeaders(context, { requestId: buildRequestId("sources-detail") }),
  });
  return mapSourceRecord(envelope.data, self, activeProfile, traceability);
}

export async function registerSource(
  context: SourceFetchContext,
  draft: SourceRegistrationDraft,
  idempotencyKey: string,
  self: BootstrapContextSelf | null,
  activeProfile: BootstrapProfile | null,
  traceability: SourceTraceabilityIndex,
): Promise<SourceBrowserRecord> {
  const normalizedTags = normalizeTagInput(draft.tags);
  const payload: {
    source_type: SourceTypeApi;
    title: string;
    content: string;
    filename?: string;
    mime_type?: string;
    tags?: string[];
  } = {
    source_type: draft.sourceType,
    title: draft.title.trim(),
    content: draft.content,
    ...(draft.filename.trim() ? { filename: draft.filename.trim() } : {}),
    ...(draft.mimeType.trim() ? { mime_type: draft.mimeType.trim() } : {}),
    ...(normalizedTags.length ? { tags: normalizedTags } : {}),
  };

  const envelope = await fetchEnvelope<SourceRecordApi>("/api/v1/sources/register", {
    method: "POST",
    headers: buildHeaders(context, {
      requestId: buildRequestId("sources-register"),
      idempotencyKey,
    }),
    body: JSON.stringify(payload),
  });

  return mapSourceRecord(envelope.data, self, activeProfile, traceability);
}

export function buildDefaultSourceRegistrationDraft(activeProfile: Pick<BootstrapProfile, "role"> | null): SourceRegistrationDraft {
  const defaultType = getSourceTypeOptions(activeProfile)[0]?.value ?? "lecture_note";
  return {
    sourceType: defaultType,
    title: "",
    content: "",
    filename: "",
    mimeType: "text/markdown",
    tags: "",
  };
}

export function getSourceTypeOptions(activeProfile: Pick<BootstrapProfile, "role"> | null): SourceTypeOption[] {
  if (!activeProfile) {
    return [SOURCE_TYPE_OPTIONS.lecture_note];
  }

  switch (activeProfile.role) {
    case "instructor":
      return [
        SOURCE_TYPE_OPTIONS.lecture_note,
        SOURCE_TYPE_OPTIONS.lecture_transcript,
        SOURCE_TYPE_OPTIONS.student_question,
        SOURCE_TYPE_OPTIONS.assignment_feedback,
        SOURCE_TYPE_OPTIONS.announcement,
      ];
    case "operator":
      return [
        SOURCE_TYPE_OPTIONS.operations_note,
        SOURCE_TYPE_OPTIONS.counseling_note,
        SOURCE_TYPE_OPTIONS.announcement,
      ];
    case "validator":
      return Object.values(SOURCE_TYPE_OPTIONS);
    default:
      return [];
  }
}

export function normalizeTagInput(rawTags: string): string[] {
  return rawTags
    .split(",")
    .map((tag) => tag.trim())
    .filter(Boolean)
    .filter((tag, index, allTags) => allTags.indexOf(tag) === index);
}
