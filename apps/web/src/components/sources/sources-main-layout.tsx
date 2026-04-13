"use client";

import { useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";

import {
  getDomainLabel,
  getProfileById,
  getRoleLabel,
  getSourcesForProfile,
  type SourceRecord,
} from "@/lib/demo-data";

import { ScopeHeader } from "@/components/console/scope-header";

const sourceTypeFilters = ["전체", "Lecture Note", "Announcement", "Policy", "Class Memo"];
const sourceStatusFilters = ["전체", "Active", "Needs Sync", "Registered"];
const sourceDomainFilters = ["전체", "Academic", "Operations"];

function SourceStatusBadge({ status }: { status: SourceRecord["statusLabel"] }) {
  const styles = {
    Active: "bg-[var(--success-soft)] text-[var(--success)]",
    "Needs Sync": "bg-[var(--warning-soft)] text-[var(--warning)]",
    Registered: "bg-[var(--primary-soft)] text-[var(--primary)]",
  }[status];

  return <span className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${styles}`}>{status}</span>;
}

function EmptyPanel({ title, description }: { title: string; description: string }) {
  return (
    <div className="flex flex-1 items-center justify-center px-6 py-8">
      <div className="max-w-xl rounded-[24px] border border-dashed border-[var(--border-strong)] bg-[var(--surface-muted)] px-6 py-7">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">No matching source</p>
        <h2 className="mt-3 text-2xl font-semibold tracking-[-0.02em] text-[var(--foreground)]">{title}</h2>
        <p className="mt-3 text-sm leading-7 text-[var(--body)]">{description}</p>
      </div>
    </div>
  );
}

export function SourcesMainLayout() {
  const searchParams = useSearchParams();
  const activeProfile = getProfileById(searchParams.get("profile"));
  const sourcesAllowed = activeProfile.role === "instructor" || activeProfile.role === "operator" || activeProfile.role === "validator";
  const sourceRecords = useMemo(() => getSourcesForProfile(activeProfile.profileId), [activeProfile.profileId]);
  const [selectedSourceId, setSelectedSourceId] = useState(sourceRecords[0]?.sourceId ?? "");
  const [searchQuery, setSearchQuery] = useState("");
  const [activeTypeFilter, setActiveTypeFilter] = useState("전체");
  const [activeStatusFilter, setActiveStatusFilter] = useState("전체");
  const [activeDomainFilter, setActiveDomainFilter] = useState("전체");

  const filteredSources = useMemo(() => {
    const normalizedQuery = searchQuery.trim().toLowerCase();

    return sourceRecords.filter((record) => {
      const matchesType = activeTypeFilter === "전체" || record.sourceType === activeTypeFilter;
      const matchesStatus = activeStatusFilter === "전체" || record.statusLabel === activeStatusFilter;
      const matchesDomain = activeDomainFilter === "전체" || record.domainLabel === activeDomainFilter;
      const matchesQuery =
        normalizedQuery.length === 0 ||
        record.title.toLowerCase().includes(normalizedQuery) ||
        record.summary.toLowerCase().includes(normalizedQuery) ||
        record.originLabel.toLowerCase().includes(normalizedQuery);

      return matchesType && matchesStatus && matchesDomain && matchesQuery;
    });
  }, [activeDomainFilter, activeStatusFilter, activeTypeFilter, searchQuery, sourceRecords]);

  const displayedSourceId = useMemo(() => {
    if (filteredSources.some((record) => record.sourceId === selectedSourceId)) {
      return selectedSourceId;
    }

    return filteredSources[0]?.sourceId ?? "";
  }, [filteredSources, selectedSourceId]);

  const selectedSource = useMemo(() => {
    return filteredSources.find((record) => record.sourceId === displayedSourceId) ?? filteredSources[0];
  }, [displayedSourceId, filteredSources]);

  return (
    <div className="flex flex-1 flex-col gap-5 pb-6">
      <ScopeHeader
        title="Sources"
        description="raw source를 등록하고, 어떤 위키와 candidate가 이 자료를 바탕으로 만들어졌는지 추적하는 intake console입니다. 단순 파일 브라우저가 아니라 지식 파이프라인의 시작점을 보여줍니다."
        role={getRoleLabel(activeProfile.role)}
        course={activeProfile.courseLabel}
        classNameLabel={activeProfile.classLabel}
        domain={getDomainLabel(activeProfile.domain)}
      />

      {!sourcesAllowed ? (
        <div className="panel-card flex min-h-[520px] items-center justify-center px-6 py-8">
          <div className="max-w-2xl rounded-[24px] border border-dashed border-[var(--border-strong)] bg-[var(--surface-muted)] px-6 py-7">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">Sources access</p>
            <h2 className="mt-3 text-2xl font-semibold tracking-[-0.02em] text-[var(--foreground)]">이 화면은 자료 등록과 traceability를 위한 작업 공간입니다.</h2>
            <p className="mt-3 text-sm leading-7 text-[var(--body)]">
              학생은 Ask와 Learning에서 정리된 결과를 주로 보고, source intake와 등록 상태는 instructor, operator, validator가 각자 허용된 scope 안에서 관리합니다.
            </p>
          </div>
        </div>
      ) : (
        <div className="grid flex-1 grid-cols-1 gap-5 xl:grid-cols-[minmax(0,1fr)_340px]">
          <section className="panel-card flex min-h-[680px] flex-col overflow-hidden">
            <div className="border-b border-[var(--border)] px-5 py-5">
              <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">Source registry</p>
                  <h2 className="mt-2 text-lg font-semibold text-[var(--foreground)]">자료 등록과 조회</h2>
                  <p className="mt-2 text-sm leading-6 text-[var(--body)]">강의자료, 공지, 정책 문서, 수업 메모가 어떤 공식 지식으로 이어지는지 한곳에서 관리합니다.</p>
                </div>
                <button className="rounded-2xl bg-[var(--primary)] px-4 py-2.5 text-sm font-semibold text-white transition hover:opacity-90" type="button">
                  자료 등록
                </button>
              </div>
            </div>

            <div className="border-b border-[var(--border)] px-5 py-4">
              <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_1.4fr]">
                <label className="block" htmlFor="source-search">
                  <span className="muted-label">자료 검색</span>
                  <input
                    id="source-search"
                    type="search"
                    value={searchQuery}
                    onChange={(event) => setSearchQuery(event.target.value)}
                    placeholder="자료명, 파일명, 요약으로 검색"
                    className="mt-2 w-full rounded-2xl border border-[var(--border)] bg-[var(--surface-muted)] px-3 py-3 text-sm text-[var(--body)] outline-none"
                  />
                </label>
                <div className="grid gap-3 sm:grid-cols-3">
                  <div>
                    <p className="muted-label">Source type</p>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {sourceTypeFilters.map((filter) => {
                        const active = filter === activeTypeFilter;
                        return (
                          <button
                            key={filter}
                            type="button"
                            onClick={() => setActiveTypeFilter(filter)}
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
                  <div>
                    <p className="muted-label">Status</p>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {sourceStatusFilters.map((filter) => {
                        const active = filter === activeStatusFilter;
                        return (
                          <button
                            key={filter}
                            type="button"
                            onClick={() => setActiveStatusFilter(filter)}
                            className={`rounded-full border px-3 py-1.5 text-xs font-medium transition ${
                              active
                                ? "border-[var(--evidence)] bg-[var(--evidence-soft)] text-[var(--evidence)]"
                                : "border-[var(--border)] bg-[var(--surface)] text-[var(--body)]"
                            }`}
                          >
                            {filter}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                  <div>
                    <p className="muted-label">Domain</p>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {sourceDomainFilters.map((filter) => {
                        const active = filter === activeDomainFilter;
                        return (
                          <button
                            key={filter}
                            type="button"
                            onClick={() => setActiveDomainFilter(filter)}
                            className={`rounded-full border px-3 py-1.5 text-xs font-medium transition ${
                              active
                                ? "border-[var(--review)] bg-[var(--review-soft)] text-[var(--review)]"
                                : "border-[var(--border)] bg-[var(--surface)] text-[var(--body)]"
                            }`}
                          >
                            {filter}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <div className="border-b border-[var(--border)] px-5 py-4">
              <div className="flex items-center justify-between gap-3 text-sm text-[var(--muted)]">
                <span>등록된 자료</span>
                <span>{filteredSources.length}개 source</span>
              </div>
            </div>

            {filteredSources.length ? (
              <div className="scrollbar-thin flex-1 overflow-y-auto">
                <div className="min-w-full overflow-x-auto">
                  <table className="min-w-full border-collapse text-left text-sm">
                    <thead className="sticky top-0 z-10 bg-[var(--surface)] text-[var(--muted)]">
                      <tr className="border-b border-[var(--border)]">
                        <th className="px-5 py-3 font-semibold">자료</th>
                        <th className="px-4 py-3 font-semibold">Type</th>
                        <th className="px-4 py-3 font-semibold">Scope</th>
                        <th className="px-4 py-3 font-semibold">Status</th>
                        <th className="px-4 py-3 font-semibold">Registered</th>
                        <th className="px-4 py-3 font-semibold">Linked</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredSources.map((record) => {
                        const active = record.sourceId === displayedSourceId;
                        return (
                          <tr
                            key={record.sourceId}
                            className={`border-b border-[var(--border)] transition ${
                              active ? "bg-[var(--primary-soft)]/50" : "hover:bg-[var(--surface-muted)]"
                            }`}
                          >
                            <td className="px-5 py-4 align-top">
                              <button
                                type="button"
                                onClick={() => setSelectedSourceId(record.sourceId)}
                                aria-pressed={active}
                                aria-label={`${record.title} 상세 보기`}
                                className="min-w-[260px] rounded-[18px] text-left transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--primary)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--surface)]"
                              >
                                <p className="font-semibold text-[var(--foreground)]">{record.title}</p>
                                <p className="mt-1 text-xs leading-5 text-[var(--muted)]">{record.originLabel}</p>
                                <p className="mt-2 text-sm leading-6 text-[var(--body)]">{record.summary}</p>
                              </button>
                            </td>
                            <td className="px-4 py-4 align-top">
                              <span className="rounded-full bg-[var(--surface-muted)] px-2.5 py-1 text-[11px] font-semibold text-[var(--muted)]">
                                {record.sourceType}
                              </span>
                            </td>
                            <td className="px-4 py-4 align-top text-[var(--body)]">{record.scopeLabel}</td>
                            <td className="px-4 py-4 align-top">
                              <SourceStatusBadge status={record.statusLabel} />
                            </td>
                            <td className="px-4 py-4 align-top text-[var(--body)]">{record.registeredAt}</td>
                            <td className="px-4 py-4 align-top text-[var(--body)]">
                              <div className="flex flex-col gap-1">
                                <span>{record.linkedWikiPages.length} wiki</span>
                                <span>{record.linkedCandidates.length} candidate</span>
                              </div>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            ) : (
              <EmptyPanel
                title="현재 조건에 맞는 source가 없습니다."
                description="검색어를 넓히거나 필터를 초기화하면 이미 등록된 자료를 다시 볼 수 있습니다. 아직 자료가 없다면 첫 source를 등록해 knowledge pipeline을 시작할 수 있습니다."
              />
            )}
          </section>

          <aside className="panel-card flex min-h-[680px] flex-col overflow-hidden">
            <div className="border-b border-[var(--border)] px-5 py-5">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">Traceability panel</p>
              <h2 className="mt-2 text-lg font-semibold text-[var(--foreground)]">선택한 자료의 연결 정보</h2>
              <p className="mt-2 text-sm leading-6 text-[var(--body)]">이 source가 어떤 위키와 후보 지식으로 이어지는지, 그리고 현재 등록 상태가 어떤지 읽는 패널입니다.</p>
            </div>

            {selectedSource ? (
              <div className="scrollbar-thin flex-1 overflow-y-auto px-4 py-4">
                <div className="space-y-3">
                  <article className="rounded-[20px] border border-[var(--border)] bg-[var(--surface-muted)] px-4 py-4">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-sm font-semibold text-[var(--foreground)]">{selectedSource.title}</p>
                        <p className="mt-2 text-sm leading-6 text-[var(--body)]">{selectedSource.summary}</p>
                      </div>
                      <SourceStatusBadge status={selectedSource.statusLabel} />
                    </div>
                    <div className="mt-4 flex flex-wrap gap-2">
                      <span className="rounded-full bg-[var(--surface)] px-2.5 py-1 text-[11px] font-semibold text-[var(--muted)]">
                        {selectedSource.sourceType}
                      </span>
                      <span className="rounded-full bg-[var(--surface)] px-2.5 py-1 text-[11px] font-semibold text-[var(--muted)]">
                        {selectedSource.domainLabel}
                      </span>
                    </div>
                  </article>

                  <article className="rounded-[20px] border border-[var(--border)] bg-[var(--surface)] px-4 py-4">
                    <p className="text-sm font-semibold text-[var(--foreground)]">등록 메타데이터</p>
                    <div className="mt-4 space-y-3 rounded-[18px] border border-[var(--border)] bg-[var(--surface-muted)] px-3 py-3">
                      <div>
                        <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--muted)]">Scope</p>
                        <p className="mt-1 text-sm font-semibold text-[var(--foreground)]">{selectedSource.scopeLabel}</p>
                      </div>
                      <div>
                        <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--muted)]">Registered at</p>
                        <p className="mt-1 text-sm text-[var(--body)]">{selectedSource.registeredAt}</p>
                      </div>
                      <div>
                        <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--muted)]">Owner</p>
                        <p className="mt-1 text-sm text-[var(--body)]">{selectedSource.ownerLabel}</p>
                      </div>
                      <div>
                        <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--muted)]">Origin</p>
                        <p className="mt-1 text-sm text-[var(--body)]">{selectedSource.originLabel}</p>
                      </div>
                    </div>
                  </article>

                  <article className="rounded-[20px] border border-[var(--border)] bg-[var(--surface)] px-4 py-4">
                    <p className="text-sm font-semibold text-[var(--foreground)]">Linked wiki pages</p>
                    <p className="mt-2 text-sm leading-6 text-[var(--body)]">이 자료를 바탕으로 현재 유지되는 공식 위키 문서입니다.</p>
                    <div className="mt-4 flex flex-wrap gap-2">
                      {selectedSource.linkedWikiPages.map((page) => (
                        <span key={page} className="rounded-full bg-[var(--primary-soft)] px-2.5 py-1 text-[11px] font-semibold text-[var(--primary)]">
                          {page}
                        </span>
                      ))}
                    </div>
                  </article>

                  <article className="rounded-[20px] border border-[var(--border)] bg-[var(--surface)] px-4 py-4">
                    <p className="text-sm font-semibold text-[var(--foreground)]">Linked candidates</p>
                    <p className="mt-2 text-sm leading-6 text-[var(--body)]">이 source가 현재 review 흐름에 어떻게 연결되는지 보여주는 후보 지식입니다.</p>
                    <div className="mt-4 flex flex-wrap gap-2">
                      {selectedSource.linkedCandidates.length ? (
                        selectedSource.linkedCandidates.map((candidate) => (
                          <span key={candidate} className="rounded-full bg-[var(--review-soft)] px-2.5 py-1 text-[11px] font-semibold text-[var(--review)]">
                            {candidate}
                          </span>
                        ))
                      ) : (
                        <span className="rounded-full bg-[var(--surface-muted)] px-2.5 py-1 text-[11px] font-semibold text-[var(--muted)]">아직 연결된 candidate 없음</span>
                      )}
                    </div>
                  </article>
                </div>
              </div>
            ) : (
              <div className="flex flex-1 items-center px-4 py-5">
                <div className="rounded-[20px] border border-dashed border-[var(--border-strong)] bg-[var(--surface-muted)] px-4 py-5 text-sm leading-6 text-[var(--body)]">
                  선택된 source가 없으면 traceability 패널도 비워 둡니다. 검색 조건을 조정하거나 다른 자료를 선택하면 연결 정보가 다시 표시됩니다.
                </div>
              </div>
            )}
          </aside>
        </div>
      )}
    </div>
  );
}
