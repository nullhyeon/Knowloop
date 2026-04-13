import type { BootstrapContextSelf, BootstrapProfile } from "@/lib/context-bootstrap";
import { getDomainLabel, type KnowloopDomain } from "@/lib/demo-data";

type ApiEnvelope<T> = {
  status: string;
  data: T;
  meta?: Record<string, unknown>;
};

type MaintenanceStatusApi = "not-run" | "clean" | "warning" | "error";
type MaintenanceSeverityApi = "warning" | "error";

type MaintenanceSummaryApi = {
  errors: number;
  warnings: number;
  stale_candidates: number;
  orphan_candidate_refs: number;
  orphan_source_refs: number;
  wiki_layout_issues: number;
};

type MaintenanceStatusCheckApi = {
  code: string;
  severity: MaintenanceSeverityApi;
  entity_type: string;
  summary: string;
};

type MaintenanceReportCheckApi = {
  code: string;
  severity: MaintenanceSeverityApi;
  entity_type: string;
  entity_id: string;
  message: string;
  details: Record<string, unknown>;
};

type MaintenanceStatusPayloadApi = {
  course_id: string;
  class_id: string;
  status: MaintenanceStatusApi;
  last_run_at?: string;
  health_score: number;
  review_queue_count: number;
  summary: MaintenanceSummaryApi;
  checks: MaintenanceStatusCheckApi[];
};

type MaintenanceReportPayloadApi = {
  version: number;
  course_id: string;
  class_id: string;
  status: MaintenanceStatusApi;
  last_run_at?: string;
  health_score: number;
  review_queue_count: number;
  summary: MaintenanceSummaryApi;
  checks: MaintenanceReportCheckApi[];
};

type MaintenanceFetchContext = {
  profileId: string;
};

export type MaintenanceSeverityLabel = "Error" | "Warning" | "Info";
export type MaintenanceStatusLabel = "Healthy" | "Needs Attention" | "Not Run";

export type MaintenanceSummaryCard = {
  label: string;
  value: string;
  hint: string;
  tone: "danger" | "warning" | "success" | "neutral";
};

export type MaintenanceFinding = {
  findingId: string;
  title: string;
  severity: MaintenanceSeverityLabel;
  code: string;
  entityType: string;
  entityLabel: string;
  summary: string;
  detail: string;
  suggestedAction: string;
};

export type MaintenanceConsoleData = {
  statusLabel: MaintenanceStatusLabel;
  reportState: "report-available" | "read-only-status";
  healthScore: string;
  lastRunAt?: string;
  reviewQueueCount: string;
  summary: string;
  summaryCards: MaintenanceSummaryCard[];
  findings: MaintenanceFinding[];
  scopeLabel: string;
  generatedBy: string;
  redactionNote?: string;
};

function buildHeaders(context: MaintenanceFetchContext): HeadersInit {
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
    throw new Error(payload?.error?.message ?? payload?.error?.code ?? `Maintenance request failed with ${response.status}.`);
  }

  return (await response.json()) as ApiEnvelope<T>;
}

function formatTimestamp(value?: string): string | undefined {
  if (!value) {
    return undefined;
  }

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

function formatCount(value: number): string {
  return new Intl.NumberFormat("ko-KR").format(value);
}

function mapSeverityLabel(severity: MaintenanceSeverityApi): MaintenanceSeverityLabel {
  return severity === "error" ? "Error" : "Warning";
}

function mapStatusLabel(status: MaintenanceStatusApi): MaintenanceStatusLabel {
  switch (status) {
    case "clean":
      return "Healthy";
    case "not-run":
      return "Not Run";
    default:
      return "Needs Attention";
  }
}

function resolveScopeLabel(
  domain: KnowloopDomain,
  self: BootstrapContextSelf | null,
  activeProfile: BootstrapProfile | null,
  courseId: string,
  classId: string,
): string {
  const courseLabel = self?.courseId === courseId ? self.courseLabel : activeProfile?.courseId === courseId ? activeProfile.courseLabel : courseId;
  const classLabel = self?.classId === classId ? self.classLabel : activeProfile?.classId === classId ? activeProfile.classLabel : classId;
  const domainLabel = getDomainLabel(domain);
  return [courseLabel, classLabel, domainLabel].filter(Boolean).join(" · ");
}

function summarizeStatus(
  payload: Pick<MaintenanceStatusPayloadApi | MaintenanceReportPayloadApi, "status" | "summary" | "review_queue_count">,
  validatorView: boolean,
): string {
  if (payload.status === "not-run") {
    return validatorView
      ? "아직 이 스코프에서 maintenance report를 생성하지 않았습니다. 최신 보고서를 실행하면 stale candidate와 orphan ref를 바로 점검할 수 있습니다."
      : "아직 최신 maintenance report가 생성되지 않았습니다. validator가 보고서를 실행하면 이 화면에 읽기 전용 상태가 표시됩니다.";
  }

  if (payload.status === "clean") {
    return "현재 스코프에서는 stale candidate, orphan reference, wiki repair issue가 감지되지 않았습니다.";
  }

  const parts: string[] = [];
  if (payload.summary.errors) {
    parts.push(`오류 ${formatCount(payload.summary.errors)}건`);
  }
  if (payload.summary.warnings) {
    parts.push(`경고 ${formatCount(payload.summary.warnings)}건`);
  }
  if (payload.summary.stale_candidates) {
    parts.push(`stale candidate ${formatCount(payload.summary.stale_candidates)}건`);
  }
  if (payload.summary.orphan_candidate_refs || payload.summary.orphan_source_refs) {
    parts.push(`끊어진 참조 ${formatCount(payload.summary.orphan_candidate_refs + payload.summary.orphan_source_refs)}건`);
  }
  if (payload.summary.wiki_layout_issues) {
    parts.push(`wiki 레이아웃 이슈 ${formatCount(payload.summary.wiki_layout_issues)}건`);
  }

  return `${parts.join(", ")}이 감지되었습니다. 지금 먼저 복구해야 하는 항목을 아래 목록에서 바로 읽을 수 있습니다.`;
}

function getFindingTitle(code: string, entityType: string): string {
  switch (code) {
    case "stale_candidate":
      return "오래 열린 candidate가 남아 있습니다.";
    case "orphan_wiki_candidate_ref":
      return "위키가 존재하지 않는 candidate를 참조합니다.";
    case "orphan_wiki_source_ref":
      return "위키가 존재하지 않는 source를 참조합니다.";
    case "maintenance_report_unreadable":
      return "저장된 maintenance report를 읽을 수 없습니다.";
    case "noncanonical_wiki_page_path":
      return "위키 파일 경로가 canonical path와 다릅니다.";
    case "invalid_wiki_page_metadata":
      return "위키 메타데이터가 손상되었거나 계약을 어깁니다.";
    default:
      return `${entityType} 점검 항목에 후속 조치가 필요합니다.`;
  }
}

function getEntityTypeLabel(entityType: string): string {
  switch (entityType) {
    case "candidate":
      return "Candidate";
    case "wiki_page":
      return "Wiki Page";
    case "maintenance_report":
      return "Report";
    default:
      return entityType;
  }
}

function getSuggestedAction(code: string, validatorView: boolean): string {
  switch (code) {
    case "stale_candidate":
      return validatorView
        ? "Review로 이동해 approve, merge, drop 또는 resume-sync 중 어떤 정리가 필요한지 바로 결정하세요."
        : "강사 화면에서는 원인만 확인하고, 실제 정리는 validator가 review/workflow에서 진행합니다.";
    case "orphan_wiki_candidate_ref":
      return validatorView
        ? "Review와 Wiki를 함께 열어 끊어진 candidate ref를 정리하거나 대상 문서를 다시 연결하세요."
        : "관련 위키 문서가 끊어진 candidate를 참조하고 있습니다. validator에게 정리를 요청하세요.";
    case "orphan_wiki_source_ref":
      return validatorView
        ? "Sources와 Wiki를 함께 열어 source registry 또는 위키 근거 ref를 복구하세요."
        : "관련 위키 문서가 끊어진 source를 참조하고 있습니다. 자료 등록 상태를 함께 확인하세요.";
    case "maintenance_report_unreadable":
      return validatorView
        ? "최신 보고서를 다시 생성하고 persisted report 저장소를 점검하세요."
        : "읽기 전용 status만 확인 가능한 상태입니다. validator가 보고서를 다시 생성해야 합니다.";
    case "noncanonical_wiki_page_path":
      return validatorView
        ? "문서를 canonical class-scoped path로 옮기고 다시 maintenance report를 실행하세요."
        : "위키 문서 경로 복구가 필요합니다. validator가 위키 정비 후 다시 확인해야 합니다.";
    case "invalid_wiki_page_metadata":
      return validatorView
        ? "frontmatter와 page metadata를 수리한 뒤 다시 maintenance report를 실행하세요."
        : "위키 메타데이터 복구가 필요합니다. validator가 정비 후 다시 상태를 확인해야 합니다.";
    default:
      return validatorView ? "관련 엔티티를 확인하고 maintenance report를 다시 실행하세요." : "validator가 상세 복구 작업을 진행해야 합니다.";
  }
}

function stringifyDetailValue(value: unknown): string {
  if (value == null) {
    return "";
  }

  if (typeof value === "string") {
    return value;
  }

  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }

  return JSON.stringify(value);
}

function summarizeDetailMap(details: Record<string, unknown>): string {
  const entries = Object.entries(details)
    .filter(([, value]) => value != null && stringifyDetailValue(value))
    .slice(0, 4)
    .map(([key, value]) => `${key}: ${stringifyDetailValue(value)}`);

  if (!entries.length) {
    return "세부 detail이 비어 있습니다. report를 다시 생성해 최신 상태를 확인해 주세요.";
  }

  return entries.join(" · ");
}

function mapStatusFinding(check: MaintenanceStatusCheckApi, index: number, validatorView: boolean): MaintenanceFinding {
  return {
    findingId: `${check.code}-${index}`,
    title: getFindingTitle(check.code, check.entity_type),
    severity: mapSeverityLabel(check.severity),
    code: check.code,
    entityType: getEntityTypeLabel(check.entity_type),
    entityLabel: validatorView ? "상세 엔티티는 report에서 확인" : "민감한 엔티티 식별자는 가려집니다.",
    summary: check.summary,
    detail: check.summary,
    suggestedAction: getSuggestedAction(check.code, validatorView),
  };
}

function mapReportFinding(check: MaintenanceReportCheckApi, index: number): MaintenanceFinding {
  return {
    findingId: `${check.code}-${check.entity_id || index}`,
    title: getFindingTitle(check.code, check.entity_type),
    severity: mapSeverityLabel(check.severity),
    code: check.code,
    entityType: getEntityTypeLabel(check.entity_type),
    entityLabel: check.entity_id,
    summary: check.message,
    detail: summarizeDetailMap(check.details),
    suggestedAction: getSuggestedAction(check.code, true),
  };
}

function buildSummaryCards(
  payload: Pick<MaintenanceStatusPayloadApi | MaintenanceReportPayloadApi, "health_score" | "review_queue_count" | "summary">,
  validatorView: boolean,
): MaintenanceSummaryCard[] {
  return [
    {
      label: "Health score",
      value: formatCount(payload.health_score),
      hint: "지금 스코프의 지식 상태가 운영 가능한 수준인지 빠르게 읽는 점수입니다.",
      tone: payload.health_score >= 90 ? "success" : payload.health_score >= 70 ? "warning" : "danger",
    },
    {
      label: "Repair queue",
      value: formatCount(payload.review_queue_count),
      hint: "현재 maintenance와 함께 같이 정리해야 하는 항목 수입니다.",
      tone: payload.review_queue_count === 0 ? "success" : "neutral",
    },
    {
      label: "Errors",
      value: formatCount(payload.summary.errors),
      hint: "바로 복구가 필요한 오류 수입니다.",
      tone: payload.summary.errors > 0 ? "danger" : "success",
    },
    {
      label: validatorView ? "Warnings" : "Visibility",
      value: validatorView ? formatCount(payload.summary.warnings) : "읽기 전용",
      hint: validatorView
        ? "검토 대기 상태로 남은 경고 수입니다."
        : "강사 화면은 민감한 엔티티 식별자를 숨긴 status만 보여줍니다.",
      tone: validatorView
        ? payload.summary.warnings > 0
          ? "warning"
          : "success"
        : "neutral",
    },
  ];
}

function buildConsoleData(
  payload: MaintenanceStatusPayloadApi | MaintenanceReportPayloadApi,
  options: {
    self: BootstrapContextSelf | null;
    activeProfile: BootstrapProfile | null;
    validatorView: boolean;
  },
): MaintenanceConsoleData {
  const { self, activeProfile, validatorView } = options;
  const domain = (self?.domain ?? activeProfile?.domain ?? (validatorView ? "review" : "academic")) as KnowloopDomain;

  const findings = validatorView && "entity_id" in (payload.checks[0] ?? {})
    ? (payload.checks as MaintenanceReportCheckApi[]).map((check, index) => mapReportFinding(check, index))
    : (payload.checks as MaintenanceStatusCheckApi[]).map((check, index) => mapStatusFinding(check, index, validatorView));

  return {
    statusLabel: mapStatusLabel(payload.status),
    reportState: validatorView ? "report-available" : "read-only-status",
    healthScore: formatCount(payload.health_score),
    lastRunAt: formatTimestamp(payload.last_run_at),
    reviewQueueCount: formatCount(payload.review_queue_count),
    summary: summarizeStatus(payload, validatorView),
    summaryCards: buildSummaryCards(payload, validatorView),
    findings,
    scopeLabel: resolveScopeLabel(domain, self, activeProfile, payload.course_id, payload.class_id),
    generatedBy: validatorView ? "validator full maintenance report" : "read-only maintenance status",
    redactionNote: validatorView ? undefined : "강사 화면에서는 entity id, 내부 경로, 세부 detail을 가린 요약만 제공합니다.",
  };
}

export async function fetchMaintenanceStatus(
  context: MaintenanceFetchContext,
  self: BootstrapContextSelf | null,
  activeProfile: BootstrapProfile | null,
): Promise<MaintenanceConsoleData> {
  const envelope = await fetchEnvelope<MaintenanceStatusPayloadApi>("/api/v1/maintenance/status", {
    headers: buildHeaders(context),
  });

  return buildConsoleData(envelope.data, {
    self,
    activeProfile,
    validatorView: false,
  });
}

export async function fetchMaintenanceReport(
  context: MaintenanceFetchContext,
  self: BootstrapContextSelf | null,
  activeProfile: BootstrapProfile | null,
): Promise<MaintenanceConsoleData> {
  const envelope = await fetchEnvelope<MaintenanceReportPayloadApi>("/api/v1/maintenance/report", {
    headers: buildHeaders(context),
  });

  return buildConsoleData(envelope.data, {
    self,
    activeProfile,
    validatorView: true,
  });
}
