"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { getDomainLabel, getRoleLabel, type KnowloopRole } from "@/lib/demo-data";
import {
  fetchMaintenanceReport,
  fetchMaintenanceStatus,
  type MaintenanceConsoleData,
  type MaintenanceFinding,
  type MaintenanceSeverityLabel,
} from "@/lib/maintenance-browser";

import { useContextBootstrap } from "@/components/console/context-bootstrap-provider";
import { ScopeHeader } from "@/components/console/scope-header";

const maintenanceSeverityFilters: Array<"전체" | MaintenanceSeverityLabel> = ["전체", "Error", "Warning"];

function MaintenanceToneBadge({
  tone,
}: {
  tone: MaintenanceConsoleData["summaryCards"][number]["tone"];
}) {
  const styles = {
    danger: "bg-[var(--danger-soft)] text-[var(--danger)]",
    warning: "bg-[var(--warning-soft)] text-[var(--warning)]",
    success: "bg-[var(--success-soft)] text-[var(--success)]",
    neutral: "bg-[var(--surface-muted)] text-[var(--muted)]",
  }[tone];

  return <span className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${styles}`}>{tone}</span>;
}

function MaintenanceSeverityBadge({ severity }: { severity: MaintenanceSeverityLabel }) {
  const styles = {
    Error: "bg-[var(--danger-soft)] text-[var(--danger)]",
    Warning: "bg-[var(--warning-soft)] text-[var(--warning)]",
    Info: "bg-[var(--surface-muted)] text-[var(--muted)]",
  }[severity];

  return <span className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${styles}`}>{severity}</span>;
}

function MaintenanceStatusBanner({ data, validatorView }: { data: MaintenanceConsoleData; validatorView: boolean }) {
  const statusStyles = {
    Healthy: "border-[var(--success)] bg-[var(--success-soft)]/55",
    "Needs Attention": "border-[var(--warning)] bg-[var(--warning-soft)]/45",
    "Not Run": "border-[var(--border-strong)] bg-[var(--surface-muted)]",
  }[data.statusLabel];

  const statusCopy = {
    Healthy: "정상",
    "Needs Attention": "주의 필요",
    "Not Run": "실행 전",
  }[data.statusLabel];

  return (
    <section className={`panel-card border ${statusStyles} px-6 py-5 lg:px-7`}>
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-full bg-[var(--surface)] px-2.5 py-1 text-[11px] font-semibold text-[var(--body)]">
              Maintenance status
            </span>
            <span className="rounded-full bg-[var(--surface)] px-2.5 py-1 text-[11px] font-semibold text-[var(--body)]">
              {validatorView ? "Validator report" : "Instructor status"}
            </span>
          </div>
          <h2 className="text-xl font-semibold tracking-[-0.02em] text-[var(--foreground)]">{statusCopy}</h2>
          <p className="max-w-4xl text-sm leading-7 text-[var(--body)]">{data.summary}</p>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <div className="rounded-[20px] border border-[var(--border)] bg-[var(--surface)] px-4 py-4">
            <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--muted)]">Health score</p>
            <p className="mt-2 text-3xl font-semibold tracking-[-0.03em] text-[var(--foreground)]">{data.healthScore}</p>
            <p className="mt-1 text-xs leading-5 text-[var(--muted)]">
              {data.lastRunAt ? `마지막 실행 ${data.lastRunAt}` : "아직 이 스코프에서 maintenance report가 실행되지 않았습니다."}
            </p>
          </div>
          <div className="rounded-[20px] border border-[var(--border)] bg-[var(--surface)] px-4 py-4">
            <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--muted)]">Report mode</p>
            <p className="mt-2 text-sm font-semibold text-[var(--foreground)]">{validatorView ? "Full report" : "Read-only status"}</p>
            <p className="mt-1 text-xs leading-5 text-[var(--muted)]">
              {validatorView
                ? "validator는 최신 maintenance report를 생성하고 상세 finding을 읽습니다."
                : "instructor는 민감한 entity id를 가린 status만 읽습니다."}
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}

function MaintenanceSkeleton() {
  return (
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px] animate-pulse">
      <section className="panel-card min-h-[680px] px-5 py-5">
        <div className="h-5 w-40 rounded-full bg-[var(--surface-muted)]" />
        <div className="mt-4 h-4 w-80 rounded-full bg-[var(--surface-muted)]" />
        <div className="mt-8 space-y-3">
          {Array.from({ length: 5 }).map((_, index) => (
            <div key={index} className="rounded-[20px] border border-[var(--border)] bg-[var(--surface)] px-4 py-4">
              <div className="h-4 w-36 rounded-full bg-[var(--surface-muted)]" />
              <div className="mt-3 h-4 w-full rounded-full bg-[var(--surface-muted)]" />
              <div className="mt-2 h-4 w-4/5 rounded-full bg-[var(--surface-muted)]" />
            </div>
          ))}
        </div>
      </section>
      <aside className="panel-card min-h-[680px] px-5 py-5">
        <div className="h-5 w-32 rounded-full bg-[var(--surface-muted)]" />
        <div className="mt-4 h-4 w-full rounded-full bg-[var(--surface-muted)]" />
        <div className="mt-2 h-4 w-4/5 rounded-full bg-[var(--surface-muted)]" />
      </aside>
    </div>
  );
}

function EmptyFindingsPanel({ title, description }: { title: string; description: string }) {
  return (
    <div className="flex flex-1 items-center justify-center px-6 py-8">
      <div className="max-w-xl rounded-[24px] border border-dashed border-[var(--border-strong)] bg-[var(--surface-muted)] px-6 py-7">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">No matching finding</p>
        <h2 className="mt-3 text-2xl font-semibold tracking-[-0.02em] text-[var(--foreground)]">{title}</h2>
        <p className="mt-3 text-sm leading-7 text-[var(--body)]">{description}</p>
      </div>
    </div>
  );
}

function AccessPanel({ role }: { role: KnowloopRole | null }) {
  return (
    <div className="panel-card flex min-h-[520px] items-center justify-center px-6 py-8">
      <div className="max-w-2xl rounded-[24px] border border-dashed border-[var(--border-strong)] bg-[var(--surface-muted)] px-6 py-7">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">Maintenance access</p>
        <h2 className="mt-3 text-2xl font-semibold tracking-[-0.02em] text-[var(--foreground)]">이 화면은 유지보수 상태를 읽는 운영 surface입니다.</h2>
        <p className="mt-3 text-sm leading-7 text-[var(--body)]">
          현재 프로필은 {role ? getRoleLabel(role) : "알 수 없는 역할"}로 인식되었습니다. maintenance 전체 보고서는 validator가 보고, instructor는 읽기 전용 상태만 확인합니다.
        </p>
      </div>
    </div>
  );
}

export function MaintenanceMainLayout() {
  const { activeProfile, self, loading: bootstrapLoading, error: bootstrapError } = useContextBootstrap();
  const maintenanceAllowed = Boolean(activeProfile && ["instructor", "validator"].includes(activeProfile.role));
  const validatorView = activeProfile?.role === "validator";

  const [maintenanceData, setMaintenanceData] = useState<MaintenanceConsoleData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeSeverityFilter, setActiveSeverityFilter] = useState<"전체" | MaintenanceSeverityLabel>("전체");
  const [selectedFindingId, setSelectedFindingId] = useState("");
  const requestSequenceRef = useRef(0);

  const loadMaintenance = useCallback(async () => {
    if (!activeProfile || !maintenanceAllowed) {
      requestSequenceRef.current += 1;
      setMaintenanceData(null);
      setLoading(false);
      setError(null);
      setSelectedFindingId("");
      return;
    }

    const requestSequence = requestSequenceRef.current + 1;
    requestSequenceRef.current = requestSequence;
    setLoading(true);
    setError(null);

    try {
      const nextData = validatorView
        ? await fetchMaintenanceReport({ profileId: activeProfile.profileId }, self, activeProfile)
        : await fetchMaintenanceStatus({ profileId: activeProfile.profileId }, self, activeProfile);

      if (requestSequence !== requestSequenceRef.current) {
        return;
      }

      setMaintenanceData(nextData);
      setSelectedFindingId((current) => (nextData.findings.some((finding) => finding.findingId === current) ? current : nextData.findings[0]?.findingId ?? ""));
    } catch (caughtError) {
      if (requestSequence !== requestSequenceRef.current) {
        return;
      }
      const message = caughtError instanceof Error ? caughtError.message : "maintenance 상태를 불러오지 못했습니다.";
      setMaintenanceData(null);
      setSelectedFindingId("");
      setError(message);
    } finally {
      if (requestSequence === requestSequenceRef.current) {
        setLoading(false);
      }
    }
  }, [activeProfile, maintenanceAllowed, self, validatorView]);

  useEffect(() => {
    void loadMaintenance();
  }, [loadMaintenance]);

  const filteredFindings = useMemo(() => {
    if (!maintenanceData) {
      return [] as MaintenanceFinding[];
    }

    return maintenanceData.findings.filter((finding) => activeSeverityFilter === "전체" || finding.severity === activeSeverityFilter);
  }, [activeSeverityFilter, maintenanceData]);

  const displayedFindingId = useMemo(() => {
    if (filteredFindings.some((finding) => finding.findingId === selectedFindingId)) {
      return selectedFindingId;
    }
    return filteredFindings[0]?.findingId ?? "";
  }, [filteredFindings, selectedFindingId]);

  const selectedFinding = useMemo(() => {
    return filteredFindings.find((finding) => finding.findingId === displayedFindingId) ?? filteredFindings[0] ?? null;
  }, [displayedFindingId, filteredFindings]);

  const roleLabel = activeProfile ? getRoleLabel(activeProfile.role) : "로딩 중";
  const courseLabel = self?.courseLabel ?? activeProfile?.courseLabel ?? "과목 로딩 중";
  const classLabel = self?.classLabel ?? activeProfile?.classLabel ?? "반 로딩 중";
  const domainLabel = getDomainLabel(self?.domain ?? activeProfile?.domain ?? (validatorView ? "review" : "academic"));

  return (
    <div className="flex flex-1 flex-col gap-5 pb-6">
      <ScopeHeader
        title="Maintenance"
        description="stale candidate, orphan reference, report freshness를 읽고 어느 복구를 먼저 해야 하는지 판단하는 운영 콘솔입니다."
        role={roleLabel}
        course={courseLabel}
        classNameLabel={classLabel}
        domain={domainLabel}
      />

      {!maintenanceAllowed ? (
        <AccessPanel role={activeProfile?.role ?? null} />
      ) : bootstrapLoading || loading ? (
        <MaintenanceSkeleton />
      ) : bootstrapError ? (
        <EmptyFindingsPanel title="컨텍스트를 불러오지 못했습니다." description={bootstrapError} />
      ) : error ? (
        <EmptyFindingsPanel title="maintenance 상태를 불러오지 못했습니다." description={error} />
      ) : !maintenanceData ? (
        <EmptyFindingsPanel title="maintenance 데이터가 아직 없습니다." description="현재 스코프에서 읽을 수 있는 maintenance status가 준비되지 않았습니다." />
      ) : (
        <>
          <MaintenanceStatusBanner data={maintenanceData} validatorView={validatorView} />

          <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            {maintenanceData.summaryCards.map((card) => (
              <article key={card.label} className="panel-card px-5 py-5">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">{card.label}</p>
                    <p className="mt-3 text-3xl font-semibold tracking-[-0.03em] text-[var(--foreground)]">{card.value}</p>
                  </div>
                  <MaintenanceToneBadge tone={card.tone} />
                </div>
                <p className="mt-3 text-sm leading-6 text-[var(--body)]">{card.hint}</p>
              </article>
            ))}
          </section>

          <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
            <section className="panel-card flex min-h-[680px] flex-col overflow-hidden">
              <div className="border-b border-[var(--border)] px-5 py-5">
                <div className="flex flex-col gap-3 xl:flex-row xl:items-start xl:justify-between">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">Findings</p>
                    <h2 className="mt-2 text-lg font-semibold text-[var(--foreground)]">현재 스코프에서 먼저 봐야 할 유지보수 항목</h2>
                    <p className="mt-2 text-sm leading-6 text-[var(--body)]">
                      severity별로 stale candidate와 orphan ref를 읽고, 어떤 화면에서 복구를 시작해야 하는지 바로 판단할 수 있도록 정리한 목록입니다.
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => void loadMaintenance()}
                    disabled={!validatorView}
                    className={`rounded-2xl px-4 py-2.5 text-sm font-semibold transition ${
                      validatorView
                        ? "bg-[var(--primary)] text-white hover:opacity-90"
                        : "cursor-not-allowed border border-[var(--border)] bg-[var(--surface-muted)] text-[var(--muted)]"
                    }`}
                  >
                    {validatorView ? "최신 보고서 다시 생성" : "read-only status"}
                  </button>
                </div>
              </div>

              <div className="border-b border-[var(--border)] px-5 py-4">
                <p className="muted-label">Severity</p>
                <div className="mt-2 flex flex-wrap gap-2">
                  {maintenanceSeverityFilters.map((filter) => {
                    const active = filter === activeSeverityFilter;
                    return (
                      <button
                        key={filter}
                        type="button"
                        aria-pressed={active}
                        onClick={() => setActiveSeverityFilter(filter)}
                        className={`rounded-full border px-3 py-1.5 text-xs font-medium transition ${
                          active
                            ? "border-[var(--primary)] bg-[var(--primary-soft)] text-[var(--primary)]"
                            : "border-[var(--border)] bg-[var(--surface)] text-[var(--body)]"
                        }`}
                      >
                        {filter}
                      </button>
                    );
                  })}
                </div>
              </div>

              {filteredFindings.length ? (
                <div className="scrollbar-thin flex-1 overflow-y-auto px-4 py-4">
                  <div className="space-y-3">
                    {filteredFindings.map((finding) => {
                      const active = finding.findingId === displayedFindingId;

                      return (
                        <button
                          key={finding.findingId}
                          type="button"
                          onClick={() => setSelectedFindingId(finding.findingId)}
                          className={`w-full rounded-[20px] border px-4 py-4 text-left transition ${
                            active
                              ? "border-[var(--primary)] bg-[var(--primary-soft)]/50"
                              : "border-[var(--border)] bg-[var(--surface)] hover:border-[var(--border-strong)]"
                          }`}
                        >
                          <div className="flex items-start justify-between gap-3">
                            <div>
                              <p className="text-sm font-semibold text-[var(--foreground)]">{finding.title}</p>
                              <p className="mt-1 text-xs font-medium text-[var(--muted)]">
                                {finding.code} · {finding.entityType}
                              </p>
                            </div>
                            <MaintenanceSeverityBadge severity={finding.severity} />
                          </div>
                          <p className="mt-3 text-sm leading-6 text-[var(--body)]">{finding.summary}</p>
                          <div className="mt-3 flex flex-wrap gap-2 text-[11px] font-semibold text-[var(--muted)]">
                            <span className="rounded-full bg-[var(--surface-muted)] px-2.5 py-1">{finding.entityLabel}</span>
                          </div>
                        </button>
                      );
                    })}
                  </div>
                </div>
              ) : maintenanceData.statusLabel === "Not Run" ? (
                <EmptyFindingsPanel
                  title="아직 유지보수 보고서가 없습니다."
                  description={validatorView
                    ? "validator가 최신 보고서를 생성하면 stale candidate와 orphan ref가 여기에 표시됩니다."
                    : "현재는 read-only status만 읽고 있습니다. validator가 보고서를 실행하면 상태가 갱신됩니다."}
                />
              ) : (
                <EmptyFindingsPanel
                  title="현재 조건에 맞는 maintenance finding이 없습니다."
                  description="필터를 다시 넓혀 보거나, 현재 스코프가 clean 상태인지 우측 메타데이터에서 함께 확인해 주세요."
                />
              )}
            </section>

            <aside className="panel-card flex min-h-[680px] flex-col overflow-hidden">
              <div className="border-b border-[var(--border)] px-5 py-5">
                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">Finding detail</p>
                <h2 className="mt-2 text-lg font-semibold text-[var(--foreground)]">선택한 유지보수 항목 상세</h2>
                <p className="mt-2 text-sm leading-6 text-[var(--body)]">운영 판단에 필요한 상세 설명과 보고서 메타데이터를 함께 읽습니다.</p>
              </div>

              <div className="scrollbar-thin flex-1 overflow-y-auto px-4 py-4">
                <div className="space-y-3">
                  {selectedFinding ? (
                    <article className="rounded-[20px] border border-[var(--border)] bg-[var(--surface-muted)] px-4 py-4">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="text-sm font-semibold text-[var(--foreground)]">{selectedFinding.title}</p>
                          <p className="mt-2 text-sm leading-6 text-[var(--body)]">{selectedFinding.summary}</p>
                        </div>
                        <MaintenanceSeverityBadge severity={selectedFinding.severity} />
                      </div>
                      <div className="mt-4 grid gap-3">
                        <div className="rounded-[18px] border border-[var(--border)] bg-[var(--surface)] px-3 py-3">
                          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--muted)]">Entity</p>
                          <p className="mt-1 text-sm font-semibold text-[var(--foreground)]">{selectedFinding.entityLabel}</p>
                          <p className="mt-1 text-xs leading-5 text-[var(--muted)]">{selectedFinding.entityType}</p>
                        </div>
                        <div className="rounded-[18px] border border-[var(--border)] bg-[var(--surface)] px-3 py-3">
                          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--muted)]">Repair detail</p>
                          <p className="mt-1 text-sm leading-6 text-[var(--body)]">{selectedFinding.detail}</p>
                        </div>
                        <div className="rounded-[18px] border border-[var(--border)] bg-[var(--surface)] px-3 py-3">
                          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--muted)]">Suggested next action</p>
                          <p className="mt-1 text-sm leading-6 text-[var(--body)]">{selectedFinding.suggestedAction}</p>
                        </div>
                      </div>
                    </article>
                  ) : (
                    <div className="rounded-[20px] border border-dashed border-[var(--border-strong)] bg-[var(--surface-muted)] px-4 py-5 text-sm leading-6 text-[var(--body)]">
                      선택한 finding이 없으면 상세 영역은 비워 둡니다. 왼쪽 목록에서 항목을 선택해 주세요.
                    </div>
                  )}

                  <article className="rounded-[20px] border border-[var(--border)] bg-[var(--surface)] px-4 py-4">
                    <p className="text-sm font-semibold text-[var(--foreground)]">Report metadata</p>
                    <div className="mt-4 space-y-3 rounded-[18px] border border-[var(--border)] bg-[var(--surface-muted)] px-3 py-3">
                      <div>
                        <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--muted)]">Scope</p>
                        <p className="mt-1 text-sm font-semibold text-[var(--foreground)]">{maintenanceData.scopeLabel}</p>
                      </div>
                      <div>
                        <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--muted)]">Last run</p>
                        <p className="mt-1 text-sm text-[var(--body)]">{maintenanceData.lastRunAt ?? "아직 없음"}</p>
                      </div>
                      <div>
                        <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--muted)]">Report source</p>
                        <p className="mt-1 text-sm text-[var(--body)]">{maintenanceData.generatedBy}</p>
                      </div>
                    </div>
                    {maintenanceData.redactionNote ? (
                      <div className="mt-4 rounded-[18px] border border-[var(--border)] bg-[var(--surface-muted)] px-3 py-3">
                        <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--muted)]">Visibility</p>
                        <p className="mt-1 text-sm leading-6 text-[var(--body)]">{maintenanceData.redactionNote}</p>
                      </div>
                    ) : null}
                  </article>
                </div>
              </div>
            </aside>
          </div>
        </>
      )}
    </div>
  );
}
