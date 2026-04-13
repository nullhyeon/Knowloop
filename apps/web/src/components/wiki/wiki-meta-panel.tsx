import type { WikiPagePreview } from "@/lib/demo-data";
import { getRelatedWikiPages } from "@/lib/demo-data";

function StateBadge({ stateLabel }: { stateLabel: string }) {
  const className =
    stateLabel === "Synced"
      ? "bg-[var(--success-soft)] text-[var(--success)]"
      : "bg-[var(--warning-soft)] text-[var(--warning)]";

  return <span className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${className}`}>{stateLabel}</span>;
}

export function WikiMetaPanel({
  page,
  onSelectPage,
}: {
  page: WikiPagePreview;
  onSelectPage: (pageId: string) => void;
}) {
  const relatedPages = getRelatedWikiPages(page);

  return (
    <div className="scrollbar-thin flex-1 overflow-y-auto px-4 py-4">
      <div className="space-y-3">
        <article className="rounded-[20px] border border-[var(--border)] bg-[var(--surface-muted)] px-4 py-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-sm font-semibold text-[var(--foreground)]">문서 상태</p>
              <p className="mt-2 text-sm leading-6 text-[var(--body)]">현재 위키에 반영된 상태와 마지막 갱신 시점을 한눈에 보여줍니다.</p>
            </div>
            <StateBadge stateLabel={page.stateLabel} />
          </div>
          <div className="mt-4 space-y-3 rounded-[18px] border border-[var(--border)] bg-[var(--surface)] px-3 py-3">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--muted)]">Scope</p>
              <p className="mt-1 text-sm font-semibold text-[var(--foreground)]">{page.scopeLabel}</p>
            </div>
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--muted)]">Updated at</p>
              <p className="mt-1 text-sm text-[var(--body)]">{page.updatedAt}</p>
            </div>
          </div>
        </article>

        <article className="rounded-[20px] border border-[var(--border)] bg-[var(--surface)] px-4 py-4">
          <p className="text-sm font-semibold text-[var(--foreground)]">Source refs</p>
          <p className="mt-2 text-sm leading-6 text-[var(--body)]">이 문서를 뒷받침하는 raw source와 근거 자료입니다.</p>
          <div className="mt-4 flex flex-wrap gap-2">
            {page.sourceRefs.map((ref) => (
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
          <p className="text-sm font-semibold text-[var(--foreground)]">Candidate refs</p>
          <p className="mt-2 text-sm leading-6 text-[var(--body)]">어떤 후보 지식이 이 문서를 보강하거나 수정했는지 보여주는 연결 정보입니다.</p>
          <div className="mt-4 flex flex-wrap gap-2">
            {page.candidateRefs.length ? (
              page.candidateRefs.map((ref) => (
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

        <article className="rounded-[20px] border border-[var(--border)] bg-[var(--surface)] px-4 py-4">
          <p className="text-sm font-semibold text-[var(--foreground)]">Related pages</p>
          <p className="mt-2 text-sm leading-6 text-[var(--body)]">같은 개념 흐름이나 운영 규칙에서 함께 읽으면 좋은 공식 문서들입니다.</p>
          <div className="mt-4 space-y-3">
            {relatedPages.map((relatedPage) => (
              <button
                key={relatedPage.pageId}
                type="button"
                onClick={() => onSelectPage(relatedPage.pageId)}
                className="block rounded-[18px] border border-[var(--border)] bg-[var(--surface-muted)] px-3 py-3 transition hover:border-[var(--border-strong)]"
              >
                <div className="flex items-center justify-between gap-3">
                  <p className="text-sm font-semibold text-[var(--foreground)]">{relatedPage.title}</p>
                  <span className="rounded-full bg-[var(--surface)] px-2.5 py-1 text-[11px] font-semibold text-[var(--muted)]">
                    {relatedPage.section}
                  </span>
                </div>
                <p className="mt-2 text-sm leading-6 text-[var(--body)]">{relatedPage.summary}</p>
              </button>
            ))}
          </div>
        </article>
      </div>
    </div>
  );
}
