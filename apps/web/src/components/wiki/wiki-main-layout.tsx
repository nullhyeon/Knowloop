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

export function WikiMainLayout() {
  const searchParams = useSearchParams();
  const activeProfile = getProfileById(searchParams.get("profile"));
  const [selectedPageId, setSelectedPageId] = useState(wikiPages[0]?.pageId ?? "");

  const selectedPage = useMemo(
    () => wikiPages.find((page) => page.pageId === selectedPageId) ?? wikiPages[0],
    [selectedPageId],
  );

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

      <div className="grid flex-1 grid-cols-1 gap-5 xl:grid-cols-[280px_minmax(0,1fr)_320px]">
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
                placeholder="개념명, FAQ, 규칙으로 검색"
                className="mt-2 w-full rounded-2xl border border-[var(--border)] bg-[var(--surface-muted)] px-3 py-3 text-sm text-[var(--body)] outline-none"
              />
            </label>
            <div className="mt-3 flex flex-wrap gap-2">
              {["공식 개념", "운영 FAQ", "빠른 참고"].map((filter) => (
                <button
                  key={filter}
                  type="button"
                  className="rounded-full border border-[var(--border)] bg-[var(--surface)] px-3 py-1.5 text-xs font-medium text-[var(--body)]"
                >
                  {filter}
                </button>
              ))}
            </div>
          </div>

          <div className="scrollbar-thin flex-1 overflow-y-auto px-4 py-4">
            <div className="space-y-3">
              {wikiPages.map((page) => {
                const active = page.pageId === selectedPage.pageId;
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
                  </button>
                );
              })}
            </div>
          </div>
        </aside>

        <main className="panel-card flex min-h-[640px] flex-col overflow-hidden">
          <div className="border-b border-[var(--border)] px-6 py-5 lg:px-7">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">Official knowledge layer</p>
            <h2 className="mt-2 text-2xl font-semibold tracking-[-0.02em] text-[var(--foreground)]">{selectedPage.title}</h2>
            <p className="mt-2 text-sm leading-7 text-[var(--body)]">{selectedPage.summary}</p>
          </div>

          <div className="scrollbar-thin flex-1 overflow-y-auto px-6 py-6 lg:px-7">
            <div className="space-y-5">
              {selectedPage.body.map((paragraph) => (
                <p key={paragraph} className="text-[15px] leading-8 text-[var(--body)]">
                  {paragraph}
                </p>
              ))}
            </div>
          </div>
        </main>

        <aside className="panel-card flex min-h-[640px] flex-col overflow-hidden">
          <div className="border-b border-[var(--border)] px-5 py-5">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">Metadata and refs</p>
            <h2 className="mt-2 text-lg font-semibold text-[var(--foreground)]">이 문서의 근거</h2>
            <p className="mt-2 text-sm leading-6 text-[var(--body)]">위키가 단순 메모가 아니라 유지되는 공식 지식층임을 보여주는 패널입니다.</p>
          </div>

          <div className="scrollbar-thin flex-1 overflow-y-auto px-4 py-4">
            <div className="space-y-3">
              <article className="rounded-[20px] border border-[var(--border)] bg-[var(--surface-muted)] px-4 py-4">
                <p className="text-sm font-semibold text-[var(--foreground)]">Last updated</p>
                <p className="mt-2 text-sm leading-6 text-[var(--body)]">{selectedPage.updatedAt}</p>
              </article>

              <article className="rounded-[20px] border border-[var(--border)] bg-[var(--surface)] px-4 py-4">
                <p className="text-sm font-semibold text-[var(--foreground)]">Source refs</p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {selectedPage.sourceRefs.map((ref) => (
                    <span
                      key={ref}
                      className="rounded-full bg-[var(--surface-muted)] px-2.5 py-1 text-[11px] font-semibold text-[var(--body)]"
                    >
                      {ref}
                    </span>
                  ))}
                </div>
              </article>

              <article className="rounded-[20px] border border-[var(--border)] bg-[var(--surface)] px-4 py-4">
                <p className="text-sm font-semibold text-[var(--foreground)]">Candidate refs</p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {selectedPage.candidateRefs.length ? (
                    selectedPage.candidateRefs.map((ref) => (
                      <span
                        key={ref}
                        className="rounded-full bg-[var(--primary-soft)] px-2.5 py-1 text-[11px] font-semibold text-[var(--primary)]"
                      >
                        {ref}
                      </span>
                    ))
                  ) : (
                    <span className="rounded-full bg-[var(--surface-muted)] px-2.5 py-1 text-[11px] font-semibold text-[var(--muted)]">
                      아직 연결된 후보 없음
                    </span>
                  )}
                </div>
              </article>
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}
