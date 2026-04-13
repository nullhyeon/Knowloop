"use client";

import { useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";

import {
  getDomainLabel,
  getProfileById,
  getReviewActionsForProfile,
  getReviewCandidates,
  getRoleLabel,
  type ReviewCandidate,
} from "@/lib/demo-data";

import { ScopeHeader } from "@/components/console/scope-header";
import { ReviewPatchPreview } from "@/components/review/review-patch-preview";

const reviewStateFilters = ["전체", "Open", "Pending", "Needs Recovery", "Promoted"];
const reviewKindFilters = ["전체", "Misconception", "FAQ", "Concept Patch"];

function ReviewStateBadge({ state }: { state: ReviewCandidate["lifecycleState"] }) {
  const styles = {
    Open: "bg-[var(--review-soft)] text-[var(--review)]",
    Pending: "bg-[var(--warning-soft)] text-[var(--warning)]",
    Promoted: "bg-[var(--success-soft)] text-[var(--success)]",
    "Needs Recovery": "bg-[var(--danger-soft)] text-[var(--danger)]",
  }[state];

  return <span className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${styles}`}>{state}</span>;
}

function ConfidenceBadge({ label, confidence }: { label: string; confidence: string }) {
  return (
    <span className="rounded-full border border-[var(--border)] bg-[var(--surface-muted)] px-2.5 py-1 text-[11px] font-semibold text-[var(--body)]">
      Confidence {label} · {confidence}
    </span>
  );
}

function EmptyPanel({ title, description }: { title: string; description: string }) {
  return (
    <div className="flex flex-1 items-center justify-center px-6 py-8">
      <div className="max-w-xl rounded-[24px] border border-dashed border-[var(--border-strong)] bg-[var(--surface-muted)] px-6 py-7">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">No matching candidate</p>
        <h2 className="mt-3 text-2xl font-semibold tracking-[-0.02em] text-[var(--foreground)]">{title}</h2>
        <p className="mt-3 text-sm leading-7 text-[var(--body)]">{description}</p>
      </div>
    </div>
  );
}

export function ReviewMainLayout() {
  const searchParams = useSearchParams();
  const activeProfile = getProfileById(searchParams.get("profile"));
  const reviewAllowed = activeProfile.role === "instructor" || activeProfile.role === "operator" || activeProfile.role === "validator";
  const reviewCandidates = useMemo(() => getReviewCandidates(activeProfile.profileId), [activeProfile.profileId]);
  const [selectedCandidateId, setSelectedCandidateId] = useState(reviewCandidates[0]?.candidateId ?? "");
  const [searchQuery, setSearchQuery] = useState("");
  const [activeStateFilter, setActiveStateFilter] = useState("전체");
  const [activeKindFilter, setActiveKindFilter] = useState("전체");

  const filteredCandidates = useMemo(() => {
    const normalizedQuery = searchQuery.trim().toLowerCase();

    return reviewCandidates.filter((candidate) => {
      const matchesState = activeStateFilter === "전체" || candidate.lifecycleState === activeStateFilter;
      const matchesKind = activeKindFilter === "전체" || candidate.kind === activeKindFilter;
      const matchesQuery =
        normalizedQuery.length === 0 ||
        candidate.title.toLowerCase().includes(normalizedQuery) ||
        candidate.summary.toLowerCase().includes(normalizedQuery) ||
        candidate.targetPage.toLowerCase().includes(normalizedQuery);

      return matchesState && matchesKind && matchesQuery;
    });
  }, [activeKindFilter, activeStateFilter, reviewCandidates, searchQuery]);

  const displayedCandidateId = useMemo(() => {
    if (filteredCandidates.some((candidate) => candidate.candidateId === selectedCandidateId)) {
      return selectedCandidateId;
    }

    return filteredCandidates[0]?.candidateId ?? "";
  }, [filteredCandidates, selectedCandidateId]);

  const selectedCandidate = useMemo(() => {
    return filteredCandidates.find((candidate) => candidate.candidateId === displayedCandidateId) ?? filteredCandidates[0];
  }, [displayedCandidateId, filteredCandidates]);

  const candidateForPanel = useMemo(() => {
    if (!selectedCandidate) {
      return null;
    }

    return {
      ...selectedCandidate,
      availableActions: getReviewActionsForProfile(activeProfile.profileId, selectedCandidate),
    };
  }, [activeProfile.profileId, selectedCandidate]);

  return (
    <div className="flex flex-1 flex-col gap-5 pb-6">
      <ScopeHeader
        title="Review"
        description="후보 지식의 근거, lifecycle, patch preview를 나란히 확인하고 approve / merge / drop / resume-sync를 결정하는 지식 검토 콘솔입니다."
        role={getRoleLabel(activeProfile.role)}
        course={activeProfile.courseLabel}
        classNameLabel={activeProfile.classLabel}
        domain={getDomainLabel(activeProfile.domain)}
      />

      {!reviewAllowed ? (
        <div className="panel-card flex min-h-[520px] items-center justify-center px-6 py-8">
          <div className="max-w-2xl rounded-[24px] border border-dashed border-[var(--border-strong)] bg-[var(--surface-muted)] px-6 py-7">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">Review access</p>
            <h2 className="mt-3 text-2xl font-semibold tracking-[-0.02em] text-[var(--foreground)]">현재 역할은 review inbox를 직접 사용하지 않습니다.</h2>
            <p className="mt-3 text-sm leading-7 text-[var(--body)]">
              학생에게는 candidate inbox 대신 Ask와 Learning에서 간접 반영 결과가 보입니다. review workflow는 instructor, operator, validator가 각자
              허용된 scope 안에서 사용합니다.
            </p>
          </div>
        </div>
      ) : (
      <div className="grid flex-1 grid-cols-1 gap-5 xl:grid-cols-[320px_minmax(0,1fr)_360px]">
        <aside className="panel-card flex min-h-[680px] flex-col overflow-hidden">
          <div className="border-b border-[var(--border)] px-5 py-5">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">Review queue</p>
            <h2 className="mt-2 text-lg font-semibold text-[var(--foreground)]">후보 지식 큐</h2>
            <p className="mt-2 text-sm leading-6 text-[var(--body)]">반복 질문, 운영 FAQ, 개념 보강 후보를 같은 화면에서 검토합니다.</p>
          </div>

          <div className="border-b border-[var(--border)] px-5 py-4">
            <label className="block" htmlFor="review-search">
              <span className="muted-label">후보 검색</span>
              <input
                id="review-search"
                type="search"
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
                placeholder="후보 제목, 대상 페이지로 검색"
                className="mt-2 w-full rounded-2xl border border-[var(--border)] bg-[var(--surface-muted)] px-3 py-3 text-sm text-[var(--body)] outline-none"
              />
            </label>
            <div className="mt-3 space-y-3">
              <div>
                <p className="muted-label">Lifecycle</p>
                <div className="mt-2 flex flex-wrap gap-2">
                  {reviewStateFilters.map((filter) => {
                    const active = filter === activeStateFilter;
                    return (
                      <button
                        key={filter}
                        type="button"
                        onClick={() => setActiveStateFilter(filter)}
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
              <div>
                <p className="muted-label">Kind</p>
                <div className="mt-2 flex flex-wrap gap-2">
                  {reviewKindFilters.map((filter) => {
                    const active = filter === activeKindFilter;
                    return (
                      <button
                        key={filter}
                        type="button"
                        onClick={() => setActiveKindFilter(filter)}
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
            </div>
          </div>

          <div className="border-b border-[var(--border)] px-5 py-4">
            <div className="flex items-center justify-between gap-3 text-sm text-[var(--muted)]">
              <span>현재 큐</span>
              <span>{filteredCandidates.length}개 candidate</span>
            </div>
          </div>

          <div className="scrollbar-thin flex-1 overflow-y-auto px-4 py-4">
            {filteredCandidates.length ? (
              <div className="space-y-3">
                {filteredCandidates.map((candidate) => {
                  const active = candidate.candidateId === displayedCandidateId;
                  return (
                    <button
                      key={candidate.candidateId}
                      type="button"
                      onClick={() => setSelectedCandidateId(candidate.candidateId)}
                      className={`w-full rounded-[20px] border px-4 py-4 text-left transition ${
                        active
                          ? "border-[var(--review)] bg-[var(--review-soft)]"
                          : "border-[var(--border)] bg-[var(--surface)] hover:border-[var(--border-strong)]"
                      }`}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="text-sm font-semibold text-[var(--foreground)]">{candidate.title}</p>
                          <p className="mt-1 text-xs font-medium text-[var(--muted)]">{candidate.queueNote}</p>
                        </div>
                        <ReviewStateBadge state={candidate.lifecycleState} />
                      </div>
                      <p className="mt-3 text-sm leading-6 text-[var(--body)]">{candidate.summary}</p>
                      <div className="mt-3 flex flex-wrap gap-2">
                        <span className="rounded-full bg-[var(--surface-muted)] px-2.5 py-1 text-[11px] font-semibold text-[var(--muted)]">
                          {candidate.kind}
                        </span>
                        <ConfidenceBadge label={candidate.confidenceLabel} confidence={candidate.confidence} />
                      </div>
                    </button>
                  );
                })}
              </div>
            ) : (
              <div className="rounded-[20px] border border-dashed border-[var(--border-strong)] bg-[var(--surface-muted)] px-4 py-6 text-sm leading-6 text-[var(--body)]">
                현재 필터 조건에 맞는 candidate가 없습니다. lifecycle 또는 kind 필터를 넓히면 다시 review 대상이 표시됩니다.
              </div>
            )}
          </div>
        </aside>

        <main className="panel-card flex min-h-[680px] flex-col overflow-hidden">
          {selectedCandidate ? (
            <>
              <div className="border-b border-[var(--border)] px-6 py-5 lg:px-7">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="rounded-full bg-[var(--review-soft)] px-2.5 py-1 text-[11px] font-semibold text-[var(--review)]">
                    {selectedCandidate.kind}
                  </span>
                  <ReviewStateBadge state={selectedCandidate.lifecycleState} />
                  <ConfidenceBadge label={selectedCandidate.confidenceLabel} confidence={selectedCandidate.confidence} />
                </div>
                <h2 className="mt-3 text-2xl font-semibold tracking-[-0.02em] text-[var(--foreground)]">{selectedCandidate.title}</h2>
                <p className="mt-2 text-sm leading-7 text-[var(--body)]">{selectedCandidate.summary}</p>
                <div className="mt-4 grid gap-3 md:grid-cols-2">
                  <div className="rounded-[18px] border border-[var(--border)] bg-[var(--surface-muted)] px-4 py-4">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--muted)]">Target page</p>
                    <p className="mt-2 text-sm font-semibold text-[var(--foreground)]">{selectedCandidate.targetPage}</p>
                    <p className="mt-1 text-xs leading-5 text-[var(--muted)]">{selectedCandidate.scopeLabel}</p>
                  </div>
                  <div className="rounded-[18px] border border-[var(--border)] bg-[var(--surface-muted)] px-4 py-4">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--muted)]">Latest activity</p>
                    <p className="mt-2 text-sm font-semibold text-[var(--foreground)]">{selectedCandidate.updatedAt}</p>
                    <p className="mt-1 text-xs leading-5 text-[var(--muted)]">{selectedCandidate.queueNote}</p>
                  </div>
                </div>
              </div>

              <div className="scrollbar-thin flex-1 overflow-y-auto px-6 py-6 lg:px-7">
                <div className="space-y-5">
                  <article className="rounded-[22px] border border-[var(--border)] bg-[var(--surface-muted)] px-4 py-4">
                    <p className="text-sm font-semibold text-[var(--foreground)]">Provenance summary</p>
                    <p className="mt-2 text-sm leading-7 text-[var(--body)]">{selectedCandidate.evidenceNote}</p>
                  </article>

                  <section className="grid gap-4 xl:grid-cols-2">
                    <article className="rounded-[20px] border border-[var(--border)] bg-[var(--surface)] px-4 py-4">
                      <p className="text-sm font-semibold text-[var(--foreground)]">Source refs</p>
                      <p className="mt-2 text-sm leading-6 text-[var(--body)]">후보를 뒷받침하는 raw source와 강의/운영 자료입니다.</p>
                      <div className="mt-4 flex flex-wrap gap-2">
                        {selectedCandidate.sourceRefs.map((ref) => (
                          <span
                            key={ref}
                            className="rounded-full border border-[var(--border)] bg-[var(--surface-muted)] px-2.5 py-1 text-[11px] font-semibold text-[var(--body)]"
                          >
                            {ref}
                          </span>
                        ))}
                      </div>
                    </article>

                    <article className="rounded-[20px] border border-[var(--border)] bg-[var(--surface)] px-4 py-4">
                      <p className="text-sm font-semibold text-[var(--foreground)]">Session refs</p>
                      <p className="mt-2 text-sm leading-6 text-[var(--body)]">질문 패턴과 반복 문의가 어떤 세션에서 올라왔는지 보여주는 연결 정보입니다.</p>
                      <div className="mt-4 flex flex-wrap gap-2">
                        {selectedCandidate.sessionRefs.map((ref) => (
                          <span
                            key={ref}
                            className="rounded-full bg-[var(--surface-muted)] px-2.5 py-1 text-[11px] font-semibold text-[var(--muted)]"
                          >
                            {ref}
                          </span>
                        ))}
                      </div>
                    </article>
                  </section>

                  <article className="rounded-[20px] border border-[var(--border)] bg-[var(--surface)] px-4 py-4">
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <p className="text-sm font-semibold text-[var(--foreground)]">Audit trail</p>
                        <p className="mt-1 text-sm leading-6 text-[var(--body)]">candidate가 어떤 lifecycle을 거쳐 현재 상태에 왔는지 읽는 운영 타임라인입니다.</p>
                      </div>
                      <span className="rounded-full bg-[var(--surface-muted)] px-2.5 py-1 text-[11px] font-semibold text-[var(--muted)]">{selectedCandidate.auditEntries.length} events</span>
                    </div>
                    <div className="mt-4 space-y-3">
                      {selectedCandidate.auditEntries.map((entry) => (
                        <div key={entry.entryId} className="rounded-[18px] border border-[var(--border)] bg-[var(--surface-muted)] px-4 py-4">
                          <div className="flex items-center justify-between gap-3">
                            <p className="text-sm font-semibold text-[var(--foreground)]">{entry.label}</p>
                            <span className="text-[11px] font-semibold text-[var(--muted)]">{entry.createdAt}</span>
                          </div>
                          <p className="mt-2 text-sm leading-6 text-[var(--body)]">{entry.summary}</p>
                          <p className="mt-2 text-xs font-medium text-[var(--muted)]">actor · {entry.actor}</p>
                        </div>
                      ))}
                    </div>
                  </article>
                </div>
              </div>
            </>
          ) : (
            <EmptyPanel
              title="현재 조건에서는 검토할 candidate가 없습니다."
              description="검색어를 넓게 잡거나 lifecycle / kind 필터를 전체로 바꾸면 같은 스코프의 review 후보를 다시 볼 수 있습니다."
            />
          )}
        </main>

        <aside className="panel-card flex min-h-[680px] flex-col overflow-hidden">
          <div className="border-b border-[var(--border)] px-5 py-5">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">Patch preview and actions</p>
            <h2 className="mt-2 text-lg font-semibold text-[var(--foreground)]">승격 전 patch 검토</h2>
            <p className="mt-2 text-sm leading-6 text-[var(--body)]">candidate를 바로 승인하지 않고, 공식 위키에 어떤 지식 변화가 생기는지 먼저 읽고 결정하는 패널입니다.</p>
          </div>

          {candidateForPanel ? (
            <ReviewPatchPreview candidate={candidateForPanel} />
          ) : (
            <div className="flex flex-1 items-center px-4 py-5">
              <div className="rounded-[20px] border border-dashed border-[var(--border-strong)] bg-[var(--surface-muted)] px-4 py-5 text-sm leading-6 text-[var(--body)]">
                선택된 candidate가 없으면 patch preview와 action panel도 비워 둡니다. 필터를 조정해 review queue에서 대상을 다시 선택해 주세요.
              </div>
            </div>
          )}
        </aside>
      </div>
      )}
    </div>
  );
}

