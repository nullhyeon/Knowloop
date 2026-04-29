"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { getDomainLabel, getRoleLabel } from "@/lib/workspace-context";
import {
  approveReviewCandidate,
  createReviewMutationIdempotencyKey,
  createDefaultReviewActionDraft,
  dropReviewCandidate,
  fetchReviewCandidateDetail,
  fetchReviewCandidateList,
  fetchReviewPatchPreview,
  mergeReviewCandidate,
  resumeReviewCandidateSync,
  type ReviewAction,
  type ReviewActionDraft,
  type ReviewCandidateDetail,
  type ReviewCandidateSummary,
  type ReviewPatchPreview,
} from "@/lib/review-browser";

import { useContextBootstrap } from "@/components/console/context-bootstrap-provider";
import { ScopeHeader } from "@/components/console/scope-header";
import { ReviewPatchPreview as ReviewPatchPreviewPanel } from "@/components/review/review-patch-preview";

function ReviewStateBadge({ state }: { state: ReviewCandidateSummary["lifecycleState"] }) {
  const styles = {
    "검토 대기": "bg-[var(--review-soft)] text-[var(--review)]",
    "승격 완료": "bg-[var(--success-soft)] text-[var(--success)]",
    "복구 필요": "bg-[var(--danger-soft)] text-[var(--danger)]",
    "병합됨": "bg-[var(--surface-muted)] text-[var(--muted)]",
    "드롭됨": "bg-[var(--warning-soft)] text-[var(--warning)]",
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

function ReviewPanelSkeleton({ count = 3 }: { count?: number }) {
  return (
    <div className="space-y-3 animate-pulse">
      {Array.from({ length: count }).map((_, index) => (
        <div key={index} className="rounded-[20px] border border-[var(--border)] bg-[var(--surface)] px-4 py-4">
          <div className="h-4 w-28 rounded-full bg-[var(--surface-muted)]" />
          <div className="mt-3 h-4 w-full rounded-full bg-[var(--surface-muted)]" />
          <div className="mt-2 h-4 w-4/5 rounded-full bg-[var(--surface-muted)]" />
        </div>
      ))}
    </div>
  );
}

export function ReviewMainLayout() {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const { activeContext, self, loading: bootstrapLoading, error: bootstrapError } = useContextBootstrap();
  const reviewAllowed = activeContext ? ["instructor", "operator", "validator"].includes(activeContext.role) : false;
  const [candidateItems, setCandidateItems] = useState<ReviewCandidateSummary[]>([]);
  const [selectedCandidateId, setSelectedCandidateId] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [activeStateFilter, setActiveStateFilter] = useState("전체");
  const [activeKindFilter, setActiveKindFilter] = useState("전체");
  const [listLoading, setListLoading] = useState(false);
  const [listError, setListError] = useState<string | null>(null);
  const [selectedCandidate, setSelectedCandidate] = useState<ReviewCandidateDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [preview, setPreview] = useState<ReviewPatchPreview | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [selectedAction, setSelectedAction] = useState<ReviewAction["action"] | null>(null);
  const [draft, setDraft] = useState<ReviewActionDraft>({
    targetPageId: "",
    targetPath: "",
    notes: "",
    mergeTargetCandidateId: "",
    dropReason: "superseded_by_existing_candidate",
  });
  const [actionLoading, setActionLoading] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);
  const [actionIdempotencyKey, setActionIdempotencyKey] = useState("");
  const listRequestRef = useRef(0);
  const detailRequestRef = useRef(0);
  const previewRequestRef = useRef(0);
  const requestedCandidateId = searchParams.get("candidate");

  const syncCandidateQuery = useCallback((candidateId: string) => {
    const nextParams = new URLSearchParams(searchParams.toString());
    if (candidateId) {
      nextParams.set("candidate", candidateId);
    } else {
      nextParams.delete("candidate");
    }
    router.replace(`${pathname}?${nextParams.toString()}`, { scroll: false });
  }, [pathname, router, searchParams]);

  const loadCandidates = useCallback(async () => {
    if (!activeContext || !reviewAllowed) {
      setCandidateItems([]);
      setListLoading(false);
      setListError(null);
      return;
    }

    const requestId = listRequestRef.current + 1;
    listRequestRef.current = requestId;
    setListLoading(true);
    setListError(null);

    try {
      const items = await fetchReviewCandidateList({ contextId: activeContext.contextId }, self, activeContext);
      if (requestId !== listRequestRef.current) {
        return;
      }
      setCandidateItems(items);
    } catch (caughtError) {
      if (requestId !== listRequestRef.current) {
        return;
      }
      const message = caughtError instanceof Error ? caughtError.message : "review 후보 목록을 불러오지 못했습니다.";
      setCandidateItems([]);
      setListError(message);
    } finally {
      if (requestId === listRequestRef.current) {
        setListLoading(false);
      }
    }
  }, [activeContext, reviewAllowed, self]);

  const runPreview = useCallback(
    async (candidate: ReviewCandidateDetail, nextDraft: ReviewActionDraft) => {
      if (!activeContext) {
        return;
      }
      if (!nextDraft.targetPageId.trim() && !nextDraft.targetPath.trim()) {
        setPreview(null);
        setPreviewError("target page id 또는 target path가 있어야 patch preview를 생성할 수 있습니다.");
        setPreviewLoading(false);
        return;
      }

      const requestId = previewRequestRef.current + 1;
      previewRequestRef.current = requestId;
      setPreviewLoading(true);
      setPreviewError(null);

      try {
        const nextPreview = await fetchReviewPatchPreview(
          { contextId: activeContext.contextId },
          candidate.candidateId,
          {
            targetPageId: nextDraft.targetPageId,
            targetPath: nextDraft.targetPath,
            notes: nextDraft.notes,
          },
        );
        if (requestId !== previewRequestRef.current) {
          return;
        }
        setPreview(nextPreview);
      } catch (caughtError) {
        if (requestId !== previewRequestRef.current) {
          return;
        }
        const message = caughtError instanceof Error ? caughtError.message : "patch preview를 불러오지 못했습니다.";
        setPreview(null);
        setPreviewError(message);
      } finally {
        if (requestId === previewRequestRef.current) {
          setPreviewLoading(false);
        }
      }
    },
    [activeContext],
  );

  const mergeOptions = useMemo(() => {
    if (!selectedCandidate) {
      return [];
    }

    return candidateItems.filter(
      (candidate) =>
        candidate.candidateId !== selectedCandidate.candidateId &&
        candidate.rawKind === selectedCandidate.rawKind &&
        candidate.rawStatus === "open" &&
        candidate.reviewDomain === selectedCandidate.reviewDomain,
    );
  }, [candidateItems, selectedCandidate]);

  const loadCandidateDetail = useCallback(
    async (candidateId: string, options?: { preserveMessages?: boolean }) => {
      if (!activeContext || !reviewAllowed || !candidateId) {
        setSelectedCandidate(null);
        setDetailLoading(false);
        setDetailError(null);
        return;
      }

      const requestId = detailRequestRef.current + 1;
      detailRequestRef.current = requestId;
      setDetailLoading(true);
      setDetailError(null);
      previewRequestRef.current += 1;
      setPreview(null);
      setPreviewLoading(false);
      setPreviewError(null);
      setSelectedAction(null);
      setActionIdempotencyKey("");
      if (!options?.preserveMessages) {
        setActionError(null);
        setActionSuccess(null);
      }

      try {
        const detail = await fetchReviewCandidateDetail({ contextId: activeContext.contextId }, candidateId, self, activeContext);
        if (requestId !== detailRequestRef.current) {
          return;
        }

        setSelectedCandidate(detail);
        const nextMergeOptions = candidateItems.filter(
          (candidate) =>
            candidate.candidateId !== detail.candidateId &&
            candidate.rawKind === detail.rawKind &&
            candidate.rawStatus === "open" &&
            candidate.reviewDomain === detail.reviewDomain,
        );
        const nextDraft = createDefaultReviewActionDraft(detail, nextMergeOptions);
        setDraft(nextDraft);

        if (detail.actionKeys.includes("patch_preview") && (nextDraft.targetPageId || nextDraft.targetPath)) {
          void runPreview(detail, nextDraft);
        }
      } catch (caughtError) {
        if (requestId !== detailRequestRef.current) {
          return;
        }
        const message = caughtError instanceof Error ? caughtError.message : "candidate 상세를 불러오지 못했습니다.";
        setSelectedCandidate(null);
        setDetailError(message);
      } finally {
        if (requestId === detailRequestRef.current) {
          setDetailLoading(false);
        }
      }
    },
    [activeContext, candidateItems, reviewAllowed, runPreview, self],
  );

  useEffect(() => {
    void loadCandidates();
  }, [loadCandidates]);

  const stateFilters = useMemo(() => ["전체", ...new Set(candidateItems.map((candidate) => candidate.lifecycleState))], [candidateItems]);
  const kindFilters = useMemo(() => ["전체", ...new Set(candidateItems.map((candidate) => candidate.kind))], [candidateItems]);

  const normalizedQuery = searchQuery.trim().toLowerCase();
  const filteredCandidates = useMemo(() => {
    return candidateItems.filter((candidate) => {
      const matchesState = activeStateFilter === "전체" || candidate.lifecycleState === activeStateFilter;
      const matchesKind = activeKindFilter === "전체" || candidate.kind === activeKindFilter;
      const matchesQuery =
        normalizedQuery.length === 0 ||
        candidate.title.toLowerCase().includes(normalizedQuery) ||
        candidate.summary.toLowerCase().includes(normalizedQuery) ||
        candidate.targetPage.toLowerCase().includes(normalizedQuery);
      return matchesState && matchesKind && matchesQuery;
    });
  }, [activeKindFilter, activeStateFilter, candidateItems, normalizedQuery]);

  const displayedCandidateId = useMemo(() => {
    if (requestedCandidateId && filteredCandidates.some((candidate) => candidate.candidateId === requestedCandidateId)) {
      return requestedCandidateId;
    }

    if (filteredCandidates.some((candidate) => candidate.candidateId === selectedCandidateId)) {
      return selectedCandidateId;
    }
    return filteredCandidates[0]?.candidateId ?? "";
  }, [filteredCandidates, requestedCandidateId, selectedCandidateId]);

  useEffect(() => {
    if (!displayedCandidateId) {
      setSelectedCandidate(null);
      setDetailLoading(false);
      previewRequestRef.current += 1;
      setPreview(null);
      setPreviewLoading(false);
      setPreviewError(null);
      setSelectedAction(null);
      setActionIdempotencyKey("");
      return;
    }

    void loadCandidateDetail(displayedCandidateId);
  }, [displayedCandidateId, loadCandidateDetail]);

  useEffect(() => {
    if (!selectedAction || !selectedCandidate || selectedAction === "patch_preview") {
      setActionIdempotencyKey("");
      return;
    }

    setActionIdempotencyKey(createReviewMutationIdempotencyKey(selectedAction, selectedCandidate.candidateId));
  }, [selectedAction, selectedCandidate]);

  const handleRunAction = useCallback(async () => {
    if (!activeContext || !selectedCandidate || !selectedAction) {
      return;
    }
    if (selectedAction === "merge" && !draft.mergeTargetCandidateId.trim()) {
      setActionError("병합 대상 candidate를 먼저 선택해 주세요.");
      return;
    }
    if (!actionIdempotencyKey) {
      setActionError("이 action에 대한 mutation key를 아직 준비하지 못했습니다. 다시 시도해 주세요.");
      return;
    }

    setActionLoading(true);
    setActionError(null);
    setActionSuccess(null);

    try {
      let result;
      switch (selectedAction) {
        case "approve":
          result = await approveReviewCandidate(
            { contextId: activeContext.contextId },
            selectedCandidate.candidateId,
            {
              targetPageId: draft.targetPageId,
              targetPath: draft.targetPath,
              notes: draft.notes,
            },
            actionIdempotencyKey,
            self,
            activeContext,
          );
          break;
        case "merge":
          result = await mergeReviewCandidate(
            { contextId: activeContext.contextId },
            selectedCandidate.candidateId,
            {
              targetCandidateId: draft.mergeTargetCandidateId,
              notes: draft.notes,
            },
            actionIdempotencyKey,
            self,
            activeContext,
          );
          break;
        case "drop":
          result = await dropReviewCandidate(
            { contextId: activeContext.contextId },
            selectedCandidate.candidateId,
            {
              reason: draft.dropReason,
              notes: draft.notes,
            },
            actionIdempotencyKey,
            self,
            activeContext,
          );
          break;
        case "resume_sync":
          result = await resumeReviewCandidateSync(
            { contextId: activeContext.contextId },
            selectedCandidate.candidateId,
            { notes: draft.notes },
            actionIdempotencyKey,
            self,
            activeContext,
          );
          break;
        default:
          result = null;
      }

      if (!result) {
        return;
      }

      await loadCandidates();
      setSelectedCandidateId(result.candidate.candidateId);
      syncCandidateQuery(result.candidate.candidateId);
      await loadCandidateDetail(result.candidate.candidateId, { preserveMessages: true });
      setActionSuccess(result.summary);
      setSelectedAction(null);
      setActionIdempotencyKey("");
    } catch (caughtError) {
      const message = caughtError instanceof Error ? caughtError.message : "review action을 실행하지 못했습니다.";
      setActionError(message);
    } finally {
      setActionLoading(false);
    }
  }, [actionIdempotencyKey, activeContext, draft, loadCandidateDetail, loadCandidates, selectedAction, selectedCandidate, self, syncCandidateQuery]);

  const roleLabel = activeContext ? getRoleLabel(activeContext.role) : "로딩 중";
  const courseLabel = self?.courseLabel ?? activeContext?.courseLabel ?? "과목 로딩 중";
  const classLabel = self?.classLabel ?? activeContext?.classLabel ?? "반 로딩 중";
  const domainLabel = getDomainLabel((self?.domain ?? activeContext?.domain ?? "review") as Parameters<typeof getDomainLabel>[0]);

  return (
    <div className="flex flex-1 flex-col gap-5 pb-6">
      <ScopeHeader
        title="Review"
        description="후보 지식의 근거, lifecycle, patch preview를 나란히 확인하고 approve / merge / drop / resume-sync를 결정하는 지식 검토 콘솔입니다."
        role={roleLabel}
        course={courseLabel}
        classNameLabel={classLabel}
        domain={domainLabel}
      />

      {!reviewAllowed ? (
        <div className="panel-card flex min-h-[520px] items-center justify-center px-6 py-8">
          <div className="max-w-2xl rounded-[24px] border border-dashed border-[var(--border-strong)] bg-[var(--surface-muted)] px-6 py-7">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">Review access</p>
            <h2 className="mt-3 text-2xl font-semibold tracking-[-0.02em] text-[var(--foreground)]">현재 역할은 review inbox를 직접 사용하지 않습니다.</h2>
            <p className="mt-3 text-sm leading-7 text-[var(--body)]">
              학생에게는 candidate inbox 대신 Ask와 Learning에서 간접 반영 결과가 보입니다. review workflow는 instructor, operator, validator가 각자 허용된 scope 안에서 사용합니다.
            </p>
          </div>
        </div>
      ) : (
        <div className="grid flex-1 grid-cols-1 gap-5 xl:grid-cols-[320px_minmax(0,1fr)_360px]">
          <aside className="panel-card flex min-h-[680px] flex-col overflow-hidden">
            <div className="border-b border-[var(--border)] px-5 py-5">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">Review queue</p>
              <h2 className="mt-2 text-lg font-semibold text-[var(--foreground)]">후보 지식 큐</h2>
              <p className="mt-2 text-sm leading-6 text-[var(--body)]">실제 review API에서 열린 후보와 복구 대기 후보를 읽고 작업하는 운영 큐입니다.</p>
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
                  className="mt-2 w-full rounded-2xl border border-[var(--border)] bg-[var(--surface-muted)] px-3 py-3 text-sm text-[var(--body)] outline-none focus-visible:border-[var(--primary)] focus-visible:ring-2 focus-visible:ring-[var(--primary-soft)]"
                />
              </label>
              <div className="mt-3 space-y-3">
                <div>
                  <p className="muted-label">Lifecycle</p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {stateFilters.map((filter) => {
                      const active = filter === activeStateFilter;
                      return (
                        <button
                          key={filter}
                          type="button"
                          aria-pressed={active}
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
                    {kindFilters.map((filter) => {
                      const active = filter === activeKindFilter;
                      return (
                        <button
                          key={filter}
                          type="button"
                          aria-pressed={active}
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
              {bootstrapLoading || listLoading ? (
                <ReviewPanelSkeleton />
              ) : bootstrapError ? (
                <div className="rounded-[20px] border border-dashed border-[var(--danger)] bg-[var(--danger-soft)]/50 px-4 py-6 text-sm leading-6 text-[var(--body)]">
                  review 화면에 필요한 컨텍스트를 불러오지 못했습니다. {bootstrapError}
                </div>
              ) : listError ? (
                <div className="rounded-[20px] border border-dashed border-[var(--danger)] bg-[var(--danger-soft)]/50 px-4 py-6 text-sm leading-6 text-[var(--body)]">
                  실제 review 후보 목록을 불러오지 못했습니다. {listError}
                </div>
              ) : filteredCandidates.length ? (
                <div className="space-y-3">
                  {filteredCandidates.map((candidate) => {
                    const active = candidate.candidateId === displayedCandidateId;
                    return (
                      <button
                        key={candidate.candidateId}
                        type="button"
                          onClick={() => {
                            setSelectedCandidateId(candidate.candidateId);
                            syncCandidateQuery(candidate.candidateId);
                          }}
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
            {detailLoading ? (
              <div className="flex-1 px-6 py-6 lg:px-7">
                <ReviewPanelSkeleton count={4} />
              </div>
            ) : selectedCandidate ? (
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
                          {selectedCandidate.sourceRefs.length ? (
                            selectedCandidate.sourceRefs.map((ref) => (
                              <span
                                key={ref}
                                className="rounded-full border border-[var(--border)] bg-[var(--surface-muted)] px-2.5 py-1 text-[11px] font-semibold text-[var(--body)]"
                              >
                                {ref}
                              </span>
                            ))
                          ) : (
                            <span className="rounded-full bg-[var(--surface-muted)] px-2.5 py-1 text-[11px] font-semibold text-[var(--muted)]">연결된 source 없음</span>
                          )}
                        </div>
                      </article>

                      <article className="rounded-[20px] border border-[var(--border)] bg-[var(--surface)] px-4 py-4">
                        <p className="text-sm font-semibold text-[var(--foreground)]">Session refs</p>
                        <p className="mt-2 text-sm leading-6 text-[var(--body)]">질문 패턴과 반복 문의가 어떤 세션에서 올라왔는지 보여주는 연결 정보입니다.</p>
                        <div className="mt-4 flex flex-wrap gap-2">
                          {selectedCandidate.sessionRefs.length ? (
                            selectedCandidate.sessionRefs.map((ref) => (
                              <span
                                key={ref}
                                className="rounded-full bg-[var(--surface-muted)] px-2.5 py-1 text-[11px] font-semibold text-[var(--muted)]"
                              >
                                {ref}
                              </span>
                            ))
                          ) : (
                            <span className="rounded-full bg-[var(--surface-muted)] px-2.5 py-1 text-[11px] font-semibold text-[var(--muted)]">연결된 session 없음</span>
                          )}
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
            ) : detailError ? (
              <EmptyPanel title="선택한 candidate를 열 수 없습니다." description={detailError} />
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

            {selectedCandidate ? (
              <ReviewPatchPreviewPanel
                candidate={selectedCandidate}
                preview={preview}
                previewLoading={previewLoading}
                previewError={previewError}
                selectedAction={selectedAction}
                draft={draft}
                mergeOptions={mergeOptions}
                actionLoading={actionLoading}
                actionError={actionError}
                actionSuccess={actionSuccess}
                onSelectAction={(action) => {
                  setSelectedAction(action);
                  if (!action || action === "patch_preview") {
                    setActionIdempotencyKey("");
                    return;
                  }
                  setActionIdempotencyKey(createReviewMutationIdempotencyKey(action, selectedCandidate.candidateId));
                }}
                onRunPreview={() => void runPreview(selectedCandidate, draft)}
                onRunAction={() => void handleRunAction()}
                onDraftChange={(nextDraft) => {
                  setDraft((current) => ({ ...current, ...nextDraft }));
                  if (selectedAction && selectedAction !== "patch_preview") {
                    setActionIdempotencyKey(createReviewMutationIdempotencyKey(selectedAction, selectedCandidate.candidateId));
                  }
                }}
              />
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
