"use client";

import { useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";

import {
  getDomainLabel,
  getProfileById,
  getRoleLabel,
  wikiPages,
} from "@/lib/demo-data";

import { ScopeHeader } from "@/components/console/scope-header";
import { WikiMetaPanel } from "@/components/wiki/wiki-meta-panel";

const wikiSections = ["전체", "공식 개념", "운영 FAQ", "빠른 참고"];

export function WikiMainLayout() {
  const searchParams = useSearchParams();
  const activeProfile = getProfileById(searchParams.get("profile"));
  const [selectedPageId, setSelectedPageId] = useState(wikiPages[0]?.pageId ?? "");
  const [searchQuery, setSearchQuery] = useState("");
  const [activeSection, setActiveSection] = useState("전체");

  const filteredPages = useMemo(() => {
    const normalizedQuery = searchQuery.trim().toLowerCase();

    return wikiPages.filter((page) => {
      const matchesSection = activeSection === "전체" || page.section === activeSection;
      const matchesQuery =
        normalizedQuery.length === 0 ||
        page.title.toLowerCase().includes(normalizedQuery) ||
        page.summary.toLowerCase().includes(normalizedQuery) ||
        page.body.some((paragraph) => paragraph.toLowerCase().includes(normalizedQuery));

      return matchesSection && matchesQuery;
    });
  }, [activeSection, searchQuery]);

  const displayedPageId = useMemo(() => {
    if (filteredPages.some((page) => page.pageId === selectedPageId)) {
      return selectedPageId;
    }

    return filteredPages[0]?.pageId ?? "";
  }, [filteredPages, selectedPageId]);

  const selectedPage = useMemo(() => {
    return filteredPages.find((page) => page.pageId === displayedPageId) ?? filteredPages[0];
  }, [displayedPageId, filteredPages]);

  function handleSelectPage(pageId: string) {
    setSearchQuery("");
    setActiveSection("전체");
    setSelectedPageId(pageId);
  }

  return (
    <div className="flex flex-1 flex-col gap-5 pb-6">
      <ScopeHeader
        title="Wiki"
        description="공식 위키를 탐색하고, 각 문서가 어떤 source와 candidate를 바탕으로 유지되는지 확인하는 지식 브라우저입니다."
        role={getRoleLabel(activeProfile.role)}
        course={activeProfile.courseLabel}
        classNameLabel={activeProfile.classLabel}
        domain={getDomainLabel(activeProfile.domain)}
      />

      <div className="grid flex-1 grid-cols-1 gap-5 xl:grid-cols-[300px_minmax(0,1fr)_340px]">
        <aside className="panel-card flex min-h-[640px] flex-col overflow-hidden">
          <div className="border-b border-[var(--border)] px-5 py-5">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">Browse pages</p>
            <h2 className="mt-2 text-lg font-semibold text-[var(--foreground)]">공식 문서 탐색</h2>
            <p className="mt-2 text-sm leading-6 text-[var(--body)]">공식 개념, FAQ, 빠른 참고 문서를 한곳에서 탐색합니다.</p>
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
                className="mt-2 w-full rounded-2xl border border-[var(--border)] bg-[var(--surface-muted)] px-3 py-3 text-sm text-[var(--body)] outline-none"
              />
            </label>
            <div className="mt-3 flex flex-wrap gap-2">
              {wikiSections.map((filter) => {
                const active = filter === activeSection;
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
            {filteredPages.length ? (
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
                          {page.stateLabel}
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
          {selectedPage ? (
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
                  이 문서는 candidate review와 source trace를 거쳐 유지되는 공식 위키 층입니다. 학생 답변, 강사 전달 문장, 운영 FAQ가 모두 이 공식 문서를 기준으로 안정화됩니다.
                </div>
                <div className="mt-6 space-y-5">
                  {selectedPage.body.map((paragraph) => (
                    <p key={paragraph} className="text-[15px] leading-8 text-[var(--body)]">
                      {paragraph}
                    </p>
                  ))}
                </div>
              </div>
            </>
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

          {selectedPage ? (
            <WikiMetaPanel page={selectedPage} onSelectPage={handleSelectPage} />
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
