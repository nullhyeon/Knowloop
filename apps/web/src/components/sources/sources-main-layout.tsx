"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { getDomainLabel, getRoleLabel } from "@/lib/demo-data";
import {
  buildDefaultSourceRegistrationDraft,
  buildSourceRegistrationFingerprint,
  createSourceRegistrationIdempotencyKey,
  fetchSourceCatalog,
  fetchSourceDetail,
  fetchSourceTraceability,
  getSourceTypeOptions,
  registerSource,
  type SourceBrowserRecord,
  type SourceRegistrationDraft,
  type SourceStatusLabel,
} from "@/lib/sources-browser";

import { useContextBootstrap } from "@/components/console/context-bootstrap-provider";
import { ScopeHeader } from "@/components/console/scope-header";

type SourceTraceabilityIndex = Awaited<ReturnType<typeof fetchSourceTraceability>>;

function createEmptyTraceability(): SourceTraceabilityIndex {
  return { wikiBySourceId: {}, candidateBySourceId: {} };
}

function SourceStatusBadge({ status }: { status: SourceStatusLabel }) {
  const styles = {
    Active: "bg-[var(--success-soft)] text-[var(--success)]",
    "Needs Sync": "bg-[var(--warning-soft)] text-[var(--warning)]",
    Registered: "bg-[var(--primary-soft)] text-[var(--primary)]",
  }[status];

  return <span className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${styles}`}>{status}</span>;
}

function SourcesSkeleton() {
  return (
    <div className="space-y-3 animate-pulse px-4 py-4">
      {Array.from({ length: 5 }).map((_, index) => (
        <div key={index} className="rounded-[20px] border border-[var(--border)] bg-[var(--surface)] px-4 py-4">
          <div className="h-4 w-28 rounded-full bg-[var(--surface-muted)]" />
          <div className="mt-3 h-4 w-full rounded-full bg-[var(--surface-muted)]" />
          <div className="mt-2 h-4 w-4/5 rounded-full bg-[var(--surface-muted)]" />
        </div>
      ))}
    </div>
  );
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
  const { activeProfile, self, loading: bootstrapLoading, error: bootstrapError } = useContextBootstrap();
  const sourcesAllowed = Boolean(activeProfile && ["instructor", "operator", "validator"].includes(activeProfile.role));
  const canRegister = activeProfile?.role === "instructor" || activeProfile?.role === "operator";

  const [sourceRecords, setSourceRecords] = useState<SourceBrowserRecord[]>([]);
  const [selectedSourceId, setSelectedSourceId] = useState("");
  const [selectedSource, setSelectedSource] = useState<SourceBrowserRecord | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [activeTypeFilter, setActiveTypeFilter] = useState("전체");
  const [activeStatusFilter, setActiveStatusFilter] = useState("전체");
  const [activeDomainFilter, setActiveDomainFilter] = useState("전체");
  const [catalogLoading, setCatalogLoading] = useState(false);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [traceability, setTraceability] = useState<SourceTraceabilityIndex>(createEmptyTraceability());
  const [traceabilityWarning, setTraceabilityWarning] = useState<string | null>(null);
  const [registerMode, setRegisterMode] = useState(false);
  const [registerDraft, setRegisterDraft] = useState<SourceRegistrationDraft>(buildDefaultSourceRegistrationDraft(activeProfile));
  const [registerLoading, setRegisterLoading] = useState(false);
  const [registerError, setRegisterError] = useState<string | null>(null);
  const [registerSuccess, setRegisterSuccess] = useState<string | null>(null);
  const [registerFingerprint, setRegisterFingerprint] = useState("");
  const [registerIdempotencyKey, setRegisterIdempotencyKey] = useState(createSourceRegistrationIdempotencyKey());
  const catalogRequestRef = useRef(0);
  const detailRequestRef = useRef(0);

  useEffect(() => {
    setRegisterDraft(buildDefaultSourceRegistrationDraft(activeProfile));
    setRegisterFingerprint("");
    setRegisterIdempotencyKey(createSourceRegistrationIdempotencyKey());
    setRegisterMode(false);
    setRegisterError(null);
    setRegisterSuccess(null);
  }, [activeProfile]);
  const loadCatalog = useCallback(async () => {
    if (!activeProfile || !sourcesAllowed) {
      catalogRequestRef.current += 1;
      detailRequestRef.current += 1;
      setCatalogLoading(false);
      setCatalogError(null);
      setTraceability(createEmptyTraceability());
      setTraceabilityWarning(null);
      setSourceRecords([]);
      setSelectedSourceId("");
      setSelectedSource(null);
      return;
    }

    const requestId = catalogRequestRef.current + 1;
    catalogRequestRef.current = requestId;
    setCatalogLoading(true);
    setCatalogError(null);
    setTraceabilityWarning(null);

    let nextTraceability = createEmptyTraceability();

    try {
      try {
        nextTraceability = await fetchSourceTraceability({ profileId: activeProfile.profileId }, self, activeProfile);
      } catch (caughtError) {
        const message = caughtError instanceof Error ? caughtError.message : "wiki 또는 candidate 연결 정보를 일부 불러오지 못했습니다.";
        nextTraceability = createEmptyTraceability();
        if (requestId === catalogRequestRef.current) {
          setTraceabilityWarning(message);
        }
      }

      const nextRecords = await fetchSourceCatalog({ profileId: activeProfile.profileId }, self, activeProfile, nextTraceability);
      if (requestId !== catalogRequestRef.current) return;

      setTraceability(nextTraceability);
      setSourceRecords(nextRecords);
      setSelectedSourceId((current) => (nextRecords.some((record) => record.sourceId === current) ? current : nextRecords[0]?.sourceId ?? ""));
    } catch (caughtError) {
      if (requestId !== catalogRequestRef.current) return;
      const message = caughtError instanceof Error ? caughtError.message : "source registry를 불러오지 못했습니다.";
      setCatalogError(message);
      setTraceability(createEmptyTraceability());
      setSourceRecords([]);
      setSelectedSourceId("");
    } finally {
      if (requestId === catalogRequestRef.current) {
        setCatalogLoading(false);
      }
    }
  }, [activeProfile, self, sourcesAllowed]);

  useEffect(() => {
    void loadCatalog();
  }, [loadCatalog]);

  const typeFilters = useMemo(() => ["전체", ...new Set(sourceRecords.map((record) => record.sourceTypeLabel))], [sourceRecords]);
  const statusFilters = useMemo(() => ["전체", ...new Set(sourceRecords.map((record) => record.statusLabel))], [sourceRecords]);
  const domainFilters = useMemo(() => ["전체", ...new Set(sourceRecords.map((record) => record.domainLabel))], [sourceRecords]);
  const effectiveTypeFilter = typeFilters.includes(activeTypeFilter) ? activeTypeFilter : "전체";
  const effectiveStatusFilter = statusFilters.includes(activeStatusFilter) ? activeStatusFilter : "전체";
  const effectiveDomainFilter = domainFilters.includes(activeDomainFilter) ? activeDomainFilter : "전체";
  const normalizedQuery = searchQuery.trim().toLowerCase();

  const filteredSources = useMemo(() => {
    return sourceRecords.filter((record) => {
      const matchesType = effectiveTypeFilter === "전체" || record.sourceTypeLabel === effectiveTypeFilter;
      const matchesStatus = effectiveStatusFilter === "전체" || record.statusLabel === effectiveStatusFilter;
      const matchesDomain = effectiveDomainFilter === "전체" || record.domainLabel === effectiveDomainFilter;
      const matchesQuery =
        normalizedQuery.length === 0 ||
        record.title.toLowerCase().includes(normalizedQuery) ||
        record.summary.toLowerCase().includes(normalizedQuery) ||
        record.originLabel.toLowerCase().includes(normalizedQuery) ||
        record.scopeLabel.toLowerCase().includes(normalizedQuery) ||
        record.tags.some((tag) => tag.toLowerCase().includes(normalizedQuery));

      return matchesType && matchesStatus && matchesDomain && matchesQuery;
    });
  }, [effectiveDomainFilter, effectiveStatusFilter, effectiveTypeFilter, normalizedQuery, sourceRecords]);

  const displayedSourceId = useMemo(() => {
    if (filteredSources.some((record) => record.sourceId === selectedSourceId)) {
      return selectedSourceId;
    }
    return filteredSources[0]?.sourceId ?? "";
  }, [filteredSources, selectedSourceId]);

  useEffect(() => {
    if (!activeProfile || !sourcesAllowed || !displayedSourceId) {
      detailRequestRef.current += 1;
      setSelectedSource(null);
      setDetailLoading(false);
      setDetailError(null);
      return;
    }

    const requestId = detailRequestRef.current + 1;
    detailRequestRef.current = requestId;
    setDetailLoading(true);
    setDetailError(null);

    void fetchSourceDetail({ profileId: activeProfile.profileId }, displayedSourceId, self, activeProfile, traceability)
      .then((detail) => {
        if (requestId !== detailRequestRef.current) return;
        setSelectedSource(detail);
      })
      .catch((caughtError) => {
        if (requestId !== detailRequestRef.current) return;
        const message = caughtError instanceof Error ? caughtError.message : "source 상세를 불러오지 못했습니다.";
        setSelectedSource(null);
        setDetailError(message);
      })
      .finally(() => {
        if (requestId === detailRequestRef.current) {
          setDetailLoading(false);
        }
      });
  }, [activeProfile, displayedSourceId, self, sourcesAllowed, traceability]);

  async function handleRegisterSource() {
    if (!activeProfile || !canRegister) return;

    if (!registerDraft.title.trim() || !registerDraft.content.trim()) {
      setRegisterError("자료 제목과 본문은 반드시 입력해야 합니다.");
      return;
    }

    const nextFingerprint = buildSourceRegistrationFingerprint(registerDraft);
    let nextKey = registerIdempotencyKey;
    if (!nextKey || registerFingerprint !== nextFingerprint) {
      nextKey = createSourceRegistrationIdempotencyKey();
      setRegisterIdempotencyKey(nextKey);
      setRegisterFingerprint(nextFingerprint);
    }

    setRegisterLoading(true);
    setRegisterError(null);
    setRegisterSuccess(null);

    try {
      const createdSource = await registerSource(
        { profileId: activeProfile.profileId },
        registerDraft,
        nextKey,
        self,
        activeProfile,
        traceability,
      );

      setSelectedSourceId(createdSource.sourceId);
      setRegisterMode(false);
      setRegisterSuccess(`${createdSource.title} 자료를 source registry에 등록했습니다.`);
      setRegisterDraft(buildDefaultSourceRegistrationDraft(activeProfile));
      setRegisterFingerprint("");
      setRegisterIdempotencyKey(createSourceRegistrationIdempotencyKey());
      await loadCatalog();
    } catch (caughtError) {
      const message = caughtError instanceof Error ? caughtError.message : "자료 등록을 완료하지 못했습니다.";
      setRegisterError(message);
    } finally {
      setRegisterLoading(false);
    }
  }

  const roleLabel = activeProfile ? getRoleLabel(activeProfile.role) : "로딩 중";
  const courseLabel = self?.courseLabel ?? activeProfile?.courseLabel ?? "과목 로딩 중";
  const classLabel = self?.classLabel ?? activeProfile?.classLabel ?? "반 로딩 중";
  const domainLabel = getDomainLabel(self?.domain ?? activeProfile?.domain ?? "academic");
  const profileId = activeProfile?.profileId ?? null;
  function renderDetailPanel() {
    if (detailLoading) {
      return <SourcesSkeleton />;
    }

    if (detailError) {
      return (
        <div className="px-4 py-5 text-sm leading-6 text-[var(--body)]">
          <div className="rounded-[20px] border border-dashed border-[var(--danger)] bg-[var(--danger-soft)]/50 px-4 py-5">
            선택한 자료 상세를 불러오지 못했습니다. {detailError}
          </div>
        </div>
      );
    }

    if (!selectedSource) {
      return (
        <div className="px-4 py-5 text-sm leading-6 text-[var(--body)]">
          <div className="rounded-[20px] border border-dashed border-[var(--border-strong)] bg-[var(--surface-muted)] px-4 py-5">
            선택된 source가 없으면 traceability 패널도 비워 둡니다. 검색 조건을 조정하거나 다른 자료를 선택하면 연결 정보가 다시 표시됩니다.
          </div>
        </div>
      );
    }

    return (
      <div className="scrollbar-thin flex-1 overflow-y-auto px-4 py-4">
        <div className="space-y-3">
          {registerSuccess ? <div className="rounded-[20px] border border-[var(--success)] bg-[var(--success-soft)]/60 px-4 py-4 text-sm leading-6 text-[var(--body)]">{registerSuccess}</div> : null}
          {traceabilityWarning ? <div className="rounded-[20px] border border-[var(--warning)] bg-[var(--warning-soft)]/60 px-4 py-4 text-sm leading-6 text-[var(--body)]">source 목록은 실제 API에서 불러왔지만, wiki 또는 candidate 연결 정보 일부를 읽지 못했습니다. {traceabilityWarning}</div> : null}
          <article className="rounded-[20px] border border-[var(--border)] bg-[var(--surface-muted)] px-4 py-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-sm font-semibold text-[var(--foreground)]">{selectedSource.title}</p>
                <p className="mt-2 text-sm leading-6 text-[var(--body)]">{selectedSource.summary}</p>
              </div>
              <SourceStatusBadge status={selectedSource.statusLabel} />
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              <span className="rounded-full bg-[var(--surface)] px-2.5 py-1 text-[11px] font-semibold text-[var(--muted)]">{selectedSource.sourceTypeLabel}</span>
              <span className="rounded-full bg-[var(--surface)] px-2.5 py-1 text-[11px] font-semibold text-[var(--muted)]">{selectedSource.domainLabel}</span>
            </div>
          </article>
          <article className="rounded-[20px] border border-[var(--border)] bg-[var(--surface)] px-4 py-4 text-sm leading-6 text-[var(--body)]">
            <p className="text-sm font-semibold text-[var(--foreground)]">등록 메타데이터</p>
            <div className="mt-4 space-y-3 rounded-[18px] border border-[var(--border)] bg-[var(--surface-muted)] px-3 py-3">
              <div><p className="muted-label">Scope</p><p className="mt-1 font-semibold text-[var(--foreground)]">{selectedSource.scopeLabel}</p></div>
              <div><p className="muted-label">Registered at</p><p className="mt-1">{selectedSource.registeredAt}</p></div>
              <div><p className="muted-label">Owner</p><p className="mt-1">{selectedSource.ownerLabel}</p></div>
              <div><p className="muted-label">Origin</p><p className="mt-1">{selectedSource.originLabel}</p></div>
              <div><p className="muted-label">Stored path</p><p className="mt-1 break-all">{selectedSource.storedPath}</p></div>
            </div>
          </article>
          <article className="rounded-[20px] border border-[var(--border)] bg-[var(--surface)] px-4 py-4">
            <p className="text-sm font-semibold text-[var(--foreground)]">Linked wiki pages</p>
            <div className="mt-4 flex flex-wrap gap-2">
              {selectedSource.linkedWikiPages.length ? selectedSource.linkedWikiPages.map((page) => profileId ? <Link key={page.pageId} href={`/wiki?profile=${profileId}&page=${page.pageId}`} className="rounded-full bg-[var(--primary-soft)] px-2.5 py-1 text-[11px] font-semibold text-[var(--primary)]">{page.title}</Link> : <span key={page.pageId} className="rounded-full bg-[var(--primary-soft)] px-2.5 py-1 text-[11px] font-semibold text-[var(--primary)]">{page.title}</span>) : <span className="rounded-full bg-[var(--surface-muted)] px-2.5 py-1 text-[11px] font-semibold text-[var(--muted)]">아직 연결된 wiki 없음</span>}
            </div>
          </article>
          <article className="rounded-[20px] border border-[var(--border)] bg-[var(--surface)] px-4 py-4">
            <p className="text-sm font-semibold text-[var(--foreground)]">Linked candidates</p>
            <div className="mt-4 space-y-2">
              {selectedSource.linkedCandidates.length ? selectedSource.linkedCandidates.map((candidate) => <div key={candidate.candidateId} className="rounded-[16px] border border-[var(--border)] bg-[var(--surface-muted)] px-3 py-3"><div className="flex items-center justify-between gap-3">{profileId ? <Link href={`/review?profile=${profileId}&candidate=${candidate.candidateId}`} className="text-sm font-semibold text-[var(--foreground)] hover:text-[var(--primary)]">{candidate.title}</Link> : <p className="text-sm font-semibold text-[var(--foreground)]">{candidate.title}</p>}<span className="rounded-full bg-[var(--review-soft)] px-2.5 py-1 text-[11px] font-semibold text-[var(--review)]">{candidate.lifecycleState}</span></div><p className="mt-2 text-xs font-medium text-[var(--muted)]">{candidate.kindLabel}</p></div>) : <span className="rounded-full bg-[var(--surface-muted)] px-2.5 py-1 text-[11px] font-semibold text-[var(--muted)]">아직 연결된 candidate 없음</span>}
            </div>
          </article>
        </div>
      </div>
    );
  }

  function renderRegisterPanel() {
    if (!activeProfile || !canRegister) return null;
    const sourceTypeOptions = getSourceTypeOptions({ role: activeProfile.role === "operator" ? "operator" : "instructor" });

    return (
      <div className="scrollbar-thin flex-1 overflow-y-auto px-4 py-4">
        <div className="space-y-3">
          <div className="rounded-[20px] border border-[var(--border)] bg-[var(--surface-muted)] px-4 py-4 text-sm leading-6 text-[var(--body)]">강의 또는 운영 자료를 raw source로 등록하면 이후 Ask, Review, Wiki 흐름에서 이 자료를 근거로 사용할 수 있습니다.</div>
          <label className="block rounded-[20px] border border-[var(--border)] bg-[var(--surface)] px-4 py-4"><span className="muted-label">Source type</span><select value={registerDraft.sourceType} onChange={(event) => setRegisterDraft((current) => ({ ...current, sourceType: event.target.value as SourceRegistrationDraft["sourceType"] }))} className="mt-2 w-full rounded-2xl border border-[var(--border)] bg-[var(--surface-muted)] px-3 py-3 text-sm text-[var(--body)] outline-none focus-visible:border-[var(--primary)] focus-visible:ring-2 focus-visible:ring-[var(--primary-soft)]">{sourceTypeOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select><p className="mt-2 text-xs leading-5 text-[var(--muted)]">{sourceTypeOptions.find((option) => option.value === registerDraft.sourceType)?.hint}</p></label>
          <label className="block rounded-[20px] border border-[var(--border)] bg-[var(--surface)] px-4 py-4"><span className="muted-label">자료 제목</span><input type="text" value={registerDraft.title} onChange={(event) => setRegisterDraft((current) => ({ ...current, title: event.target.value }))} placeholder="예: 3주차 chain rule 강의 노트" className="mt-2 w-full rounded-2xl border border-[var(--border)] bg-[var(--surface-muted)] px-3 py-3 text-sm text-[var(--body)] outline-none focus-visible:border-[var(--primary)] focus-visible:ring-2 focus-visible:ring-[var(--primary-soft)]" /></label>
          <div className="grid gap-3 md:grid-cols-2"><label className="block rounded-[20px] border border-[var(--border)] bg-[var(--surface)] px-4 py-4"><span className="muted-label">파일명</span><input type="text" value={registerDraft.filename} onChange={(event) => setRegisterDraft((current) => ({ ...current, filename: event.target.value }))} placeholder="week-03-chain-rule.md" className="mt-2 w-full rounded-2xl border border-[var(--border)] bg-[var(--surface-muted)] px-3 py-3 text-sm text-[var(--body)] outline-none focus-visible:border-[var(--primary)] focus-visible:ring-2 focus-visible:ring-[var(--primary-soft)]" /></label><label className="block rounded-[20px] border border-[var(--border)] bg-[var(--surface)] px-4 py-4"><span className="muted-label">MIME type</span><input type="text" value={registerDraft.mimeType} onChange={(event) => setRegisterDraft((current) => ({ ...current, mimeType: event.target.value }))} placeholder="text/markdown" className="mt-2 w-full rounded-2xl border border-[var(--border)] bg-[var(--surface-muted)] px-3 py-3 text-sm text-[var(--body)] outline-none focus-visible:border-[var(--primary)] focus-visible:ring-2 focus-visible:ring-[var(--primary-soft)]" /></label></div>
          <label className="block rounded-[20px] border border-[var(--border)] bg-[var(--surface)] px-4 py-4"><span className="muted-label">태그</span><input type="text" value={registerDraft.tags} onChange={(event) => setRegisterDraft((current) => ({ ...current, tags: event.target.value }))} placeholder="미분, 체인룰, 3주차" className="mt-2 w-full rounded-2xl border border-[var(--border)] bg-[var(--surface-muted)] px-3 py-3 text-sm text-[var(--body)] outline-none focus-visible:border-[var(--primary)] focus-visible:ring-2 focus-visible:ring-[var(--primary-soft)]" /></label>
          <label className="block rounded-[20px] border border-[var(--border)] bg-[var(--surface)] px-4 py-4"><span className="muted-label">자료 본문</span><textarea value={registerDraft.content} onChange={(event) => setRegisterDraft((current) => ({ ...current, content: event.target.value }))} placeholder="실제 source 본문을 붙여 넣어 주세요." rows={14} className="mt-2 w-full rounded-2xl border border-[var(--border)] bg-[var(--surface-muted)] px-3 py-3 text-sm leading-6 text-[var(--body)] outline-none focus-visible:border-[var(--primary)] focus-visible:ring-2 focus-visible:ring-[var(--primary-soft)]" /></label>
          {registerError ? <div className="rounded-[20px] border border-[var(--danger)] bg-[var(--danger-soft)]/50 px-4 py-4 text-sm leading-6 text-[var(--body)]">자료 등록을 완료하지 못했습니다. {registerError}</div> : null}
          <div className="flex flex-wrap justify-end gap-3"><button type="button" onClick={() => { setRegisterMode(false); setRegisterError(null); }} className="rounded-2xl border border-[var(--border)] px-4 py-2.5 text-sm font-semibold text-[var(--body)] transition hover:border-[var(--border-strong)]">취소</button><button type="button" onClick={() => void handleRegisterSource()} disabled={registerLoading} className="rounded-2xl bg-[var(--primary)] px-4 py-2.5 text-sm font-semibold text-white transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60">{registerLoading ? "등록 중..." : "자료 등록"}</button></div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-1 flex-col gap-5 pb-6">
      <ScopeHeader title="Sources" description="raw source를 등록하고, 어떤 위키와 candidate가 이 자료를 바탕으로 만들어졌는지 추적하는 intake console입니다. 단순 파일 브라우저가 아니라 지식 파이프라인의 시작점을 보여줍니다." role={roleLabel} course={courseLabel} classNameLabel={classLabel} domain={domainLabel} />
      {!sourcesAllowed ? <div className="panel-card flex min-h-[520px] items-center justify-center px-6 py-8"><div className="max-w-2xl rounded-[24px] border border-dashed border-[var(--border-strong)] bg-[var(--surface-muted)] px-6 py-7"><p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">Sources access</p><h2 className="mt-3 text-2xl font-semibold tracking-[-0.02em] text-[var(--foreground)]">이 화면은 자료 등록과 traceability를 위한 작업 공간입니다.</h2><p className="mt-3 text-sm leading-7 text-[var(--body)]">학생은 Ask와 Learning에서 정리된 결과를 주로 보고, source intake와 등록 상태는 instructor, operator, validator가 각자 허용된 scope 안에서 관리합니다.</p></div></div> : <div className="grid flex-1 grid-cols-1 gap-5 xl:grid-cols-[minmax(0,1fr)_360px]"><section className="panel-card flex min-h-[680px] flex-col overflow-hidden"><div className="border-b border-[var(--border)] px-5 py-5"><div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between"><div><p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">Source registry</p><h2 className="mt-2 text-lg font-semibold text-[var(--foreground)]">자료 등록과 조회</h2><p className="mt-2 text-sm leading-6 text-[var(--body)]">실제 source registry에서 자료를 읽고, 어떤 공식 지식과 review 후보로 이어지는지 traceability를 함께 확인합니다.</p></div>{canRegister ? <button className="rounded-2xl bg-[var(--primary)] px-4 py-2.5 text-sm font-semibold text-white transition hover:opacity-90" type="button" onClick={() => { setRegisterMode(true); setRegisterError(null); setRegisterSuccess(null); }}>자료 등록</button> : <div className="rounded-[18px] border border-[var(--border)] bg-[var(--surface-muted)] px-4 py-3 text-xs font-semibold text-[var(--muted)]">validator는 등록 대신 traceability 확인만 가능합니다.</div>}</div></div><div className="border-b border-[var(--border)] px-5 py-4"><div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_1.4fr]"><label className="block" htmlFor="source-search"><span className="muted-label">자료 검색</span><input id="source-search" type="search" value={searchQuery} onChange={(event) => setSearchQuery(event.target.value)} placeholder="자료명, 파일명, 요약, scope로 검색" className="mt-2 w-full rounded-2xl border border-[var(--border)] bg-[var(--surface-muted)] px-3 py-3 text-sm text-[var(--body)] outline-none focus-visible:border-[var(--primary)] focus-visible:ring-2 focus-visible:ring-[var(--primary-soft)]" /></label><div className="grid gap-3 sm:grid-cols-3"><div><p className="muted-label">Source type</p><div className="mt-2 flex flex-wrap gap-2">{typeFilters.map((filter) => { const active = filter === effectiveTypeFilter; return <button key={filter} type="button" aria-pressed={active} onClick={() => setActiveTypeFilter(filter)} className={`rounded-full border px-3 py-1.5 text-xs font-medium transition ${active ? "border-[var(--primary)] bg-[var(--primary-soft)] text-[var(--primary)]" : "border-[var(--border)] bg-[var(--surface)] text-[var(--body)]"}`}>{filter}</button>; })}</div></div><div><p className="muted-label">Status</p><div className="mt-2 flex flex-wrap gap-2">{statusFilters.map((filter) => { const active = filter === effectiveStatusFilter; return <button key={filter} type="button" aria-pressed={active} onClick={() => setActiveStatusFilter(filter)} className={`rounded-full border px-3 py-1.5 text-xs font-medium transition ${active ? "border-[var(--evidence)] bg-[var(--evidence-soft)] text-[var(--evidence)]" : "border-[var(--border)] bg-[var(--surface)] text-[var(--body)]"}`}>{filter}</button>; })}</div></div><div><p className="muted-label">Domain</p><div className="mt-2 flex flex-wrap gap-2">{domainFilters.map((filter) => { const active = filter === effectiveDomainFilter; return <button key={filter} type="button" aria-pressed={active} onClick={() => setActiveDomainFilter(filter)} className={`rounded-full border px-3 py-1.5 text-xs font-medium transition ${active ? "border-[var(--review)] bg-[var(--review-soft)] text-[var(--review)]" : "border-[var(--border)] bg-[var(--surface)] text-[var(--body)]"}`}>{filter}</button>; })}</div></div></div></div></div><div className="border-b border-[var(--border)] px-5 py-4"><div className="flex items-center justify-between gap-3 text-sm text-[var(--muted)]"><span>등록된 자료</span><span>{filteredSources.length}개 source</span></div></div>{bootstrapLoading || catalogLoading ? <SourcesSkeleton /> : bootstrapError ? <EmptyPanel title="컨텍스트를 불러오지 못했습니다." description={bootstrapError} /> : catalogError ? <EmptyPanel title="source registry를 불러오지 못했습니다." description={catalogError} /> : filteredSources.length ? <div className="scrollbar-thin flex-1 overflow-y-auto"><div className="min-w-full overflow-x-auto"><table className="min-w-full border-collapse text-left text-sm"><thead className="sticky top-0 z-10 bg-[var(--surface)] text-[var(--muted)]"><tr className="border-b border-[var(--border)]"><th className="px-5 py-3 font-semibold">자료</th><th className="px-4 py-3 font-semibold">Type</th><th className="px-4 py-3 font-semibold">Scope</th><th className="px-4 py-3 font-semibold">Status</th><th className="px-4 py-3 font-semibold">Registered</th><th className="px-4 py-3 font-semibold">Linked</th></tr></thead><tbody>{filteredSources.map((record) => { const active = record.sourceId === displayedSourceId; return <tr key={record.sourceId} className={`border-b border-[var(--border)] transition ${active ? "bg-[var(--primary-soft)]/50" : "hover:bg-[var(--surface-muted)]"}`}><td className="px-5 py-4 align-top"><button type="button" onClick={() => { setSelectedSourceId(record.sourceId); setRegisterMode(false); }} aria-pressed={active} aria-label={`${record.title} 상세 보기`} className="min-w-[260px] rounded-[18px] text-left transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--primary)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--surface)]"><p className="font-semibold text-[var(--foreground)]">{record.title}</p><p className="mt-1 text-xs leading-5 text-[var(--muted)]">{record.originLabel}</p><p className="mt-2 text-sm leading-6 text-[var(--body)]">{record.summary}</p></button></td><td className="px-4 py-4 align-top"><span className="rounded-full bg-[var(--surface-muted)] px-2.5 py-1 text-[11px] font-semibold text-[var(--muted)]">{record.sourceTypeLabel}</span></td><td className="px-4 py-4 align-top text-[var(--body)]">{record.scopeLabel}</td><td className="px-4 py-4 align-top"><SourceStatusBadge status={record.statusLabel} /></td><td className="px-4 py-4 align-top text-[var(--body)]">{record.registeredAt}</td><td className="px-4 py-4 align-top text-[var(--body)]"><div className="flex flex-col gap-1"><span>{record.linkedWikiPages.length} wiki</span><span>{record.linkedCandidates.length} candidate</span></div></td></tr>; })}</tbody></table></div></div> : <EmptyPanel title="현재 조건에 맞는 source가 없습니다." description="검색어를 넓히거나 필터를 초기화하면 이미 등록된 자료를 다시 볼 수 있습니다. 아직 자료가 없다면 첫 source를 등록해 knowledge pipeline을 시작할 수 있습니다." />}</section><aside className="panel-card flex min-h-[680px] flex-col overflow-hidden"><div className="border-b border-[var(--border)] px-5 py-5"><div className="flex items-start justify-between gap-3"><div><p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">{registerMode ? "Register source" : "Traceability panel"}</p><h2 className="mt-2 text-lg font-semibold text-[var(--foreground)]">{registerMode ? "새 raw source 등록" : "선택한 자료의 연결 정보"}</h2><p className="mt-2 text-sm leading-6 text-[var(--body)]">{registerMode ? "자료를 바로 등록하고, 이후 Ask / Review / Wiki 흐름으로 이어질 수 있게 raw source를 추가합니다." : "이 source가 어떤 위키와 후보 지식으로 이어지는지, 그리고 현재 등록 상태가 어떤지 읽는 패널입니다."}</p></div>{canRegister ? <button type="button" onClick={() => { setRegisterMode((current) => !current); setRegisterError(null); }} className="rounded-2xl border border-[var(--border)] px-3 py-2 text-xs font-semibold text-[var(--body)] transition hover:border-[var(--border-strong)]">{registerMode ? "상세 보기" : "등록 패널 열기"}</button> : null}</div></div>{registerMode && canRegister ? renderRegisterPanel() : renderDetailPanel()}</aside></div>}
    </div>
  );
}
