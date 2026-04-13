"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { getDomainLabel, getRoleLabel } from "@/lib/demo-data";
import {
  fetchWikiPageDetail,
  fetchWikiPageList,
  type WikiBodyBlock,
  type WikiBrowserDetail,
  type WikiBrowserListItem,
} from "@/lib/wiki-browser";

import { useContextBootstrap } from "@/components/console/context-bootstrap-provider";
import { ScopeHeader } from "@/components/console/scope-header";
import { WikiMetaPanel } from "@/components/wiki/wiki-meta-panel";

type WikiCatalogSnapshot = {
  profileId: string;
  items: WikiBrowserListItem[];
};

type WikiSearchSnapshot = {
  profileId: string;
  query: string;
  items: WikiBrowserListItem[];
};

type WikiErrorState = {
  profileId: string;
  query: string;
  message: string;
};

function WikiPanelSkeleton({ count = 3 }: { count?: number }) {
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

function buildDetailCacheKey(profileId: string, pageId: string) {
  return `${profileId}:${pageId}`;
}

function getOverlapScore(selectedPage: WikiBrowserDetail, candidatePage: WikiBrowserDetail): number {
  const sharedCandidates = candidatePage.candidateRefs.filter((ref) => selectedPage.candidateRefs.includes(ref)).length;
  const sharedSources = candidatePage.sourceRefs.filter((ref) => selectedPage.sourceRefs.includes(ref)).length;
  return sharedCandidates * 3 + sharedSources * 2;
}

function WikiDocumentBody({ blocks }: { blocks: WikiBodyBlock[] }) {
  return (
    <div className="mt-6 space-y-5">
      {blocks.map((block, index) => {
        if (block.kind === "heading") {
          if (block.level === 1) {
            return (
              <h3 key={`${block.kind}-${index}`} className="text-2xl font-semibold tracking-[-0.02em] text-[var(--foreground)]">
                {block.content}
              </h3>
            );
          }

          return (
            <h4 key={`${block.kind}-${index}`} className="text-lg font-semibold text-[var(--foreground)]">
              {block.content}
            </h4>
          );
        }

        if (block.kind === "list") {
          return (
            <ul key={`${block.kind}-${index}`} className="space-y-2 pl-5 text-[15px] leading-8 text-[var(--body)]">
              {block.items.map((item) => (
                <li key={item} className="list-disc">
                  {item}
                </li>
              ))}
            </ul>
          );
        }

        return (
          <p key={`${block.kind}-${index}`} className="text-[15px] leading-8 text-[var(--body)]">
            {block.content}
          </p>
        );
      })}
    </div>
  );
}

export function WikiMainLayout() {
  const { activeProfile, self, loading: bootstrapLoading, error: bootstrapError } = useContextBootstrap();
  const [selectedPageId, setSelectedPageId] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [activeSection, setActiveSection] = useState("전체");
  const [catalogSnapshot, setCatalogSnapshot] = useState<WikiCatalogSnapshot | null>(null);
  const [searchSnapshot, setSearchSnapshot] = useState<WikiSearchSnapshot | null>(null);
  const [errorState, setErrorState] = useState<WikiErrorState | null>(null);
  const [detailCache, setDetailCache] = useState<Record<string, WikiBrowserDetail>>({});
  const [detailErrors, setDetailErrors] = useState<Record<string, string>>({});
  const catalogRequestRef = useRef(0);
  const searchRequestRef = useRef(0);
  const detailRequestRef = useRef(0);

  const normalizedQuery = searchQuery.trim();

  useEffect(() => {
    if (!activeProfile) {
      return;
    }

    const requestId = catalogRequestRef.current + 1;
    catalogRequestRef.current = requestId;
    const profileId = activeProfile.profileId;

    void fetchWikiPageList({ profileId }, "", self, activeProfile)
      .then((pages) => {
        if (requestId !== catalogRequestRef.current) {
          return;
        }

        setCatalogSnapshot({ profileId, items: pages });
        setErrorState((current) => {
          if (!current || current.profileId !== profileId || current.query !== "") {
            return current;
          }
          return null;
        });
        setDetailCache((current) => {
          const allowedKeys = new Set(pages.map((page) => buildDetailCacheKey(profileId, page.pageId)));
          return Object.fromEntries(Object.entries(current).filter(([key]) => !key.startsWith(`${profileId}:`) || allowedKeys.has(key)));
        });
        setDetailErrors((current) => {
          const allowedKeys = new Set(pages.map((page) => buildDetailCacheKey(profileId, page.pageId)));
          return Object.fromEntries(Object.entries(current).filter(([key]) => !key.startsWith(`${profileId}:`) || allowedKeys.has(key)));
        });
      })
      .catch((caughtError) => {
        if (requestId !== catalogRequestRef.current) {
          return;
        }

        const message = caughtError instanceof Error ? caughtError.message : "위키 목록을 불러오지 못했습니다.";
        setErrorState({ profileId, query: "", message });
      });
  }, [activeProfile, self]);

  useEffect(() => {
    if (!activeProfile || !normalizedQuery) {
      return;
    }

    const requestId = searchRequestRef.current + 1;
    searchRequestRef.current = requestId;
    const profileId = activeProfile.profileId;

    void fetchWikiPageList({ profileId }, normalizedQuery, self, activeProfile)
      .then((pages) => {
        if (requestId !== searchRequestRef.current) {
          return;
        }

        setSearchSnapshot({ profileId, query: normalizedQuery, items: pages });
        setErrorState((current) => {
          if (!current || current.profileId !== profileId || current.query !== normalizedQuery) {
            return current;
          }
          return null;
        });
      })
      .catch((caughtError) => {
        if (requestId !== searchRequestRef.current) {
          return;
        }

        const message = caughtError instanceof Error ? caughtError.message : "위키 검색 결과를 불러오지 못했습니다.";
        setErrorState({ profileId, query: normalizedQuery, message });
      });
  }, [activeProfile, normalizedQuery, self]);

  const currentCatalogError = useMemo(() => {
    if (!activeProfile || !errorState) {
      return null;
    }

    if (errorState.profileId !== activeProfile.profileId) {
      return null;
    }

    if (errorState.query !== "") {
      return null;
    }

    return errorState.message;
  }, [activeProfile, errorState]);

  const currentSearchError = useMemo(() => {
    if (!activeProfile || !errorState || !normalizedQuery) {
      return null;
    }

    if (errorState.profileId !== activeProfile.profileId || errorState.query !== normalizedQuery) {
      return null;
    }

    return errorState.message;
  }, [activeProfile, errorState, normalizedQuery]);

  const hasFreshCatalog = Boolean(activeProfile && catalogSnapshot && catalogSnapshot.profileId === activeProfile.profileId);
  const catalogPages = useMemo(() => (hasFreshCatalog ? catalogSnapshot?.items ?? [] : []), [catalogSnapshot, hasFreshCatalog]);
  const hasFreshSearch = Boolean(
    !normalizedQuery || (activeProfile && searchSnapshot && searchSnapshot.profileId === activeProfile.profileId && searchSnapshot.query === normalizedQuery),
  );
  const activePageSet = useMemo(() => {
    if (!normalizedQuery) {
      return catalogPages;
    }

    if (!hasFreshSearch) {
      return [];
    }

    return searchSnapshot?.items ?? [];
  }, [catalogPages, hasFreshSearch, normalizedQuery, searchSnapshot]);
  const detailSourcePages = useMemo(
    () => (catalogPages.length ? catalogPages : activePageSet),
    [activePageSet, catalogPages],
  );
  const availableSections = useMemo(() => {
    const sourcePages = detailSourcePages.length ? detailSourcePages : activePageSet;
    return ["전체", ...new Set(sourcePages.map((page) => page.section))];
  }, [activePageSet, detailSourcePages]);
  const effectiveActiveSection = availableSections.includes(activeSection) ? activeSection : "전체";
  const listLoading = Boolean(
    bootstrapLoading ||
      (activeProfile &&
        (normalizedQuery
          ? !hasFreshSearch && !currentSearchError
          : !hasFreshCatalog && !currentCatalogError)),
  );
  const currentListError = normalizedQuery ? currentSearchError : currentCatalogError;

  useEffect(() => {
    if (!activeProfile || !detailSourcePages.length) {
      return;
    }

    const profileId = activeProfile.profileId;
    const pagesToPrefetch = detailSourcePages.filter((page) => {
      const cacheKey = buildDetailCacheKey(profileId, page.pageId);
      return !detailCache[cacheKey] && !detailErrors[cacheKey];
    });
    if (!pagesToPrefetch.length) {
      return;
    }

    const requestId = detailRequestRef.current + 1;
    detailRequestRef.current = requestId;

    void Promise.all(
      pagesToPrefetch.map(async (page) => {
        const cacheKey = buildDetailCacheKey(profileId, page.pageId);
        try {
          const detail = await fetchWikiPageDetail({ profileId }, page.pageId, self, activeProfile);
          return { ok: true as const, cacheKey, detail };
        } catch (caughtError) {
          const message = caughtError instanceof Error ? caughtError.message : "위키 문서를 불러오지 못했습니다.";
          return { ok: false as const, cacheKey, message };
        }
      }),
    ).then((results) => {
      if (requestId !== detailRequestRef.current) {
        return;
      }

      setDetailCache((current) => {
        const next = { ...current };
        for (const result of results) {
          if (result.ok) {
            next[result.cacheKey] = result.detail;
          }
        }
        return next;
      });

      setDetailErrors((current) => {
        const next = { ...current };
        for (const result of results) {
          if (result.ok) {
            delete next[result.cacheKey];
          } else {
            next[result.cacheKey] = result.message;
          }
        }
        return next;
      });
    });
  }, [activeProfile, detailCache, detailErrors, detailSourcePages, self]);

  const filteredPages = useMemo(() => {
    return activePageSet.filter((page) => effectiveActiveSection === "전체" || page.section === effectiveActiveSection);
  }, [activePageSet, effectiveActiveSection]);

  const displayedPageId = useMemo(() => {
    if (filteredPages.some((page) => page.pageId === selectedPageId)) {
      return selectedPageId;
    }

    return filteredPages[0]?.pageId ?? "";
  }, [filteredPages, selectedPageId]);

  const currentDetailCacheKey = activeProfile && displayedPageId ? buildDetailCacheKey(activeProfile.profileId, displayedPageId) : null;
  const selectedPage = currentDetailCacheKey ? detailCache[currentDetailCacheKey] ?? null : null;
  const currentDetailError = currentDetailCacheKey ? detailErrors[currentDetailCacheKey] ?? null : null;
  const detailLoading = Boolean(!listLoading && activeProfile && displayedPageId && !selectedPage && !currentDetailError);

  const relatedPages = useMemo(() => {
    if (!selectedPage || !activeProfile) {
      return [];
    }

    const profilePrefix = `${activeProfile.profileId}:`;
    const relationSourcePages = detailSourcePages.length ? detailSourcePages : activePageSet;
    const relatedDetails = Object.entries(detailCache)
      .filter(([cacheKey, page]) => cacheKey.startsWith(profilePrefix) && page.pageId !== selectedPage.pageId)
      .map(([, page]) => ({ page, score: getOverlapScore(selectedPage, page) }))
      .filter((candidate) => candidate.score > 0)
      .sort((left, right) => right.score - left.score)
      .slice(0, 3);

    return relatedDetails
      .map(({ page }) => relationSourcePages.find((candidate) => candidate.pageId === page.pageId))
      .filter((candidate): candidate is WikiBrowserListItem => Boolean(candidate));
  }, [activePageSet, activeProfile, detailCache, detailSourcePages, selectedPage]);

  function handleSelectPage(pageId: string) {
    setSearchQuery("");
    setActiveSection("전체");
    setSelectedPageId(pageId);
  }

  const roleLabel = activeProfile ? getRoleLabel(activeProfile.role) : "로딩 중";
  const courseLabel = self?.courseLabel ?? activeProfile?.courseLabel ?? "과목 로딩 중";
  const classLabel = self?.classLabel ?? activeProfile?.classLabel ?? "반 로딩 중";
  const domainLabel = getDomainLabel(self?.domain ?? activeProfile?.domain ?? "academic");

  return (
    <div className="flex flex-1 flex-col gap-5 pb-6">
      <ScopeHeader
        title="Wiki"
        description="공식 위키를 탐색하고, 각 문서가 어떤 source와 candidate를 바탕으로 유지되는지 확인하는 지식 브라우저입니다."
        role={roleLabel}
        course={courseLabel}
        classNameLabel={classLabel}
        domain={domainLabel}
      />

      <div className="grid flex-1 grid-cols-1 gap-5 xl:grid-cols-[300px_minmax(0,1fr)_340px]">
        <aside className="panel-card flex min-h-[640px] flex-col overflow-hidden">
          <div className="border-b border-[var(--border)] px-5 py-5">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">Browse pages</p>
            <h2 className="mt-2 text-lg font-semibold text-[var(--foreground)]">공식 문서 탐색</h2>
            <p className="mt-2 text-sm leading-6 text-[var(--body)]">실제 위키 응답의 domain 태그와 검색어를 기준으로 공식 문서를 탐색합니다.</p>
          </div>

          <div className="border-b border-[var(--border)] px-5 py-4">
            <label className="block" htmlFor="wiki-search">
              <span className="muted-label">문서 검색</span>
              <input
                id="wiki-search"
                type="search"
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
                placeholder="개념명, FAQ, 규칙으로 검색"
                className="mt-2 w-full rounded-2xl border border-[var(--border)] bg-[var(--surface-muted)] px-3 py-3 text-sm text-[var(--body)] outline-none focus-visible:border-[var(--primary)] focus-visible:ring-2 focus-visible:ring-[var(--primary-soft)]"
              />
            </label>
            <div className="mt-3 flex flex-wrap gap-2">
              {availableSections.map((filter) => {
                const active = filter === effectiveActiveSection;
                return (
                  <button
                    key={filter}
                    type="button"
                    onClick={() => setActiveSection(filter)}
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

          <div className="border-b border-[var(--border)] px-5 py-4">
            <div className="flex items-center justify-between gap-3 text-sm text-[var(--muted)]">
              <span>검색 결과</span>
              <span>{filteredPages.length}개 문서</span>
            </div>
          </div>

          <div className="scrollbar-thin flex-1 overflow-y-auto px-4 py-4">
            {listLoading ? (
              <WikiPanelSkeleton />
            ) : bootstrapError ? (
              <div className="rounded-[20px] border border-dashed border-[var(--danger)] bg-[var(--danger-soft)]/50 px-4 py-6 text-sm leading-6 text-[var(--body)]">
                현재 위키 브라우저에 필요한 컨텍스트를 불러오지 못했습니다. {bootstrapError}
              </div>
            ) : currentListError ? (
              <div className="rounded-[20px] border border-dashed border-[var(--danger)] bg-[var(--danger-soft)]/50 px-4 py-6 text-sm leading-6 text-[var(--body)]">
                실제 위키 목록을 불러오지 못했습니다. {currentListError}
              </div>
            ) : filteredPages.length ? (
              <div className="space-y-3">
                {filteredPages.map((page) => {
                  const active = page.pageId === displayedPageId;
                  return (
                    <button
                      key={page.pageId}
                      type="button"
                      onClick={() => setSelectedPageId(page.pageId)}
                      className={`w-full rounded-[20px] border px-4 py-4 text-left transition ${
                        active
                          ? "border-[var(--primary)] bg-[var(--primary-soft)]"
                          : "border-[var(--border)] bg-[var(--surface)] hover:border-[var(--border-strong)]"
                      }`}
                    >
                      <div className="flex items-center justify-between gap-3">
                        <p className="text-sm font-semibold text-[var(--foreground)]">{page.title}</p>
                        <span className="rounded-full bg-[var(--surface-muted)] px-2.5 py-1 text-[11px] font-semibold text-[var(--muted)]">
                          {page.section}
                        </span>
                      </div>
                      <p className="mt-2 text-sm leading-6 text-[var(--body)]">{page.summary}</p>
                      <div className="mt-3 flex flex-wrap gap-2">
                        <span className="rounded-full bg-[var(--surface-muted)] px-2.5 py-1 text-[11px] font-semibold text-[var(--muted)]">
                          {page.scopeLabel}
                        </span>
                        <span className="rounded-full bg-[var(--surface-muted)] px-2.5 py-1 text-[11px] font-semibold text-[var(--muted)]">
                          {page.updatedAt}
                        </span>
                      </div>
                    </button>
                  );
                })}
              </div>
            ) : (
              <div className="rounded-[20px] border border-dashed border-[var(--border-strong)] bg-[var(--surface-muted)] px-4 py-6 text-sm leading-6 text-[var(--body)]">
                현재 검색 조건에 맞는 공식 문서가 없습니다. 다른 키워드로 검색하거나 섹션 필터를 전체로 바꿔 보세요.
              </div>
            )}
          </div>
        </aside>

        <main className="panel-card flex min-h-[640px] flex-col overflow-hidden">
          {listLoading || detailLoading ? (
            <div className="flex flex-1 flex-col px-6 py-6 lg:px-7">
              <div className="animate-pulse">
                <div className="h-4 w-40 rounded-full bg-[var(--surface-muted)]" />
                <div className="mt-4 h-9 w-2/3 rounded-full bg-[var(--surface-muted)]" />
                <div className="mt-3 h-5 w-full rounded-full bg-[var(--surface-muted)]" />
                <div className="mt-2 h-5 w-4/5 rounded-full bg-[var(--surface-muted)]" />
              </div>
              <div className="mt-6 rounded-[22px] border border-[var(--border)] bg-[var(--surface-muted)] px-4 py-4">
                <div className="h-4 w-44 rounded-full bg-[var(--surface)]" />
                <div className="mt-3 h-4 w-full rounded-full bg-[var(--surface)]" />
                <div className="mt-2 h-4 w-5/6 rounded-full bg-[var(--surface)]" />
              </div>
            </div>
          ) : selectedPage ? (
            <>
              <div className="border-b border-[var(--border)] px-6 py-5 lg:px-7">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="rounded-full bg-[var(--primary-soft)] px-2.5 py-1 text-[11px] font-semibold text-[var(--primary)]">
                    {selectedPage.section}
                  </span>
                  <span className="rounded-full bg-[var(--surface-muted)] px-2.5 py-1 text-[11px] font-semibold text-[var(--muted)]">
                    {selectedPage.scopeLabel}
                  </span>
                  <span className="rounded-full bg-[var(--surface-muted)] px-2.5 py-1 text-[11px] font-semibold text-[var(--muted)]">
                    {selectedPage.updatedAt}
                  </span>
                </div>
                <h2 className="mt-3 text-2xl font-semibold tracking-[-0.02em] text-[var(--foreground)]">{selectedPage.title}</h2>
                <p className="mt-2 text-sm leading-7 text-[var(--body)]">{selectedPage.summary}</p>
              </div>

              <div className="scrollbar-thin flex-1 overflow-y-auto px-6 py-6 lg:px-7">
                <div className="rounded-[22px] border border-[var(--border)] bg-[var(--surface-muted)] px-4 py-4 text-sm leading-6 text-[var(--body)]">
                  이 문서는 실제 백엔드 위키 응답을 바탕으로 렌더되는 공식 지식 층입니다. 질문, review, source trace가 이 문서를 중심으로 이어집니다.
                </div>
                <WikiDocumentBody blocks={selectedPage.bodyBlocks} />
              </div>
            </>
          ) : displayedPageId && currentDetailError ? (
            <div className="flex flex-1 items-center justify-center px-6 py-8 lg:px-7">
              <div className="max-w-xl rounded-[24px] border border-dashed border-[var(--danger)] bg-[var(--danger-soft)]/50 px-6 py-7">
                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">Wiki detail unavailable</p>
                <h2 className="mt-3 text-2xl font-semibold tracking-[-0.02em] text-[var(--foreground)]">선택한 공식 위키 문서를 열 수 없습니다.</h2>
                <p className="mt-3 text-sm leading-7 text-[var(--body)]">{currentDetailError}</p>
              </div>
            </div>
          ) : (
            <div className="flex flex-1 items-center justify-center px-6 py-8 lg:px-7">
              <div className="max-w-xl rounded-[24px] border border-dashed border-[var(--border-strong)] bg-[var(--surface-muted)] px-6 py-7">
                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">No matching page</p>
                <h2 className="mt-3 text-2xl font-semibold tracking-[-0.02em] text-[var(--foreground)]">검색 조건에 맞는 공식 위키 문서가 아직 없습니다.</h2>
                <p className="mt-3 text-sm leading-7 text-[var(--body)]">
                  검색어를 조금 넓게 잡거나 섹션 필터를 전체로 바꾸면 이미 운영 중인 공식 문서를 다시 탐색할 수 있습니다. 아직 문서가 없다면,
                  이후 질문과 candidate review를 거쳐 새로운 공식 위키 문서로 승격될 수 있습니다.
                </p>
              </div>
            </div>
          )}
        </main>

        <aside className="panel-card flex min-h-[640px] flex-col overflow-hidden">
          <div className="border-b border-[var(--border)] px-5 py-5">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">Metadata and refs</p>
            <h2 className="mt-2 text-lg font-semibold text-[var(--foreground)]">이 문서의 근거</h2>
            <p className="mt-2 text-sm leading-6 text-[var(--body)]">위키가 단순 메모가 아니라 운영되는 공식 지식층임을 보여주는 패널입니다.</p>
          </div>

          {listLoading || detailLoading ? (
            <div className="flex-1 px-4 py-4">
              <WikiPanelSkeleton count={4} />
            </div>
          ) : selectedPage ? (
            <WikiMetaPanel page={selectedPage} relatedPages={relatedPages} onSelectPage={handleSelectPage} />
          ) : (
            <div className="flex flex-1 items-center px-4 py-5">
              <div className="rounded-[20px] border border-dashed border-[var(--border-strong)] bg-[var(--surface-muted)] px-4 py-5 text-sm leading-6 text-[var(--body)]">
                현재 선택된 공식 문서가 없어 메타데이터와 근거 패널도 비어 있습니다. 검색 조건을 조정하면 source refs, candidate refs,
                related pages가 다시 표시됩니다.
              </div>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}
