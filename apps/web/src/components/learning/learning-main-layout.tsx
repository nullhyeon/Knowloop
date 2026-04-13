"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";

import {
  getDomainLabel,
  getProfileById,
  getRoleLabel,
  learningGaps,
  learningSummaryCards,
  nextActions,
  recentSessions,
  wikiPages,
  withProfile,
} from "@/lib/demo-data";

import { ScopeHeader } from "@/components/console/scope-header";

function GapBadge({ severity }: { severity: "watch" | "focus" | "stable" }) {
  const config = {
    watch: "bg-[var(--warning-soft)] text-[var(--warning)]",
    focus: "bg-[var(--review-soft)] text-[var(--review)]",
    stable: "bg-[var(--success-soft)] text-[var(--success)]",
  }[severity];

  return <span className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${config}`}>{severity}</span>;
}

export function LearningMainLayout() {
  const searchParams = useSearchParams();
  const activeProfile = getProfileById(searchParams.get("profile"));

  return (
    <div className="flex flex-1 flex-col gap-5 pb-6">
      <ScopeHeader
        title="Learning"
        description="학생의 최근 혼동 개념, 학습 노트, 다음 복습 액션을 이어서 보는 개인 학습 콘솔입니다. 질문 기록과 공식 위키가 어떻게 복습 흐름으로 연결되는지 보여줍니다."
        role={getRoleLabel(activeProfile.role)}
        course={activeProfile.courseLabel}
        classNameLabel={activeProfile.classLabel}
        domain={getDomainLabel(activeProfile.domain)}
      />

      <section className="grid gap-4 md:grid-cols-3">
        {learningSummaryCards.map((card) => (
          <article key={card.label} className="panel-card px-5 py-5">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">{card.label}</p>
            <p className="mt-3 text-3xl font-semibold tracking-[-0.03em] text-[var(--foreground)]">{card.value}</p>
            <p className="mt-2 text-sm leading-6 text-[var(--body)]">{card.hint}</p>
          </article>
        ))}
      </section>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.1fr)_340px]">
        <section className="panel-card px-6 py-5 lg:px-7">
          <div className="space-y-1">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">Recent learning notes</p>
            <h2 className="text-lg font-semibold tracking-[-0.02em] text-[var(--foreground)]">최근 질문에서 이어진 학습 메모</h2>
            <p className="text-sm leading-7 text-[var(--body)]">질문 응답에서 생성된 학습 포인트를 다시 읽고, 같은 개념을 다음 질문으로 연결할 수 있는 영역입니다.</p>
          </div>

          <div className="mt-5 space-y-3">
            {recentSessions.map((session) => (
              <article key={session.sessionId} className="rounded-[20px] border border-[var(--border)] bg-[var(--surface-muted)] px-4 py-4">
                <div className="flex items-center justify-between gap-3">
                  <p className="text-sm font-semibold text-[var(--foreground)]">{session.title}</p>
                  <span className="text-[11px] font-semibold text-[var(--muted)]">{session.createdAt}</span>
                </div>
                <p className="mt-2 text-sm leading-6 text-[var(--body)]">{session.preview}</p>
              </article>
            ))}
          </div>

          <div className="mt-6 rounded-[24px] border border-[var(--border)] bg-[var(--surface)] px-5 py-5">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">Linked wiki pages</p>
            <h3 className="mt-2 text-lg font-semibold text-[var(--foreground)]">공식 위키와 연결된 복습 포인트</h3>
            <div className="mt-4 space-y-3">
              {wikiPages.slice(0, 2).map((page) => (
                <Link
                  key={page.pageId}
                  href={withProfile("/wiki", activeProfile.profileId)}
                  className="block rounded-[20px] border border-[var(--border)] bg-[var(--surface-muted)] px-4 py-4 transition hover:border-[var(--border-strong)]"
                >
                  <p className="text-sm font-semibold text-[var(--foreground)]">{page.title}</p>
                  <p className="mt-2 text-sm leading-6 text-[var(--body)]">{page.summary}</p>
                </Link>
              ))}
            </div>
          </div>
        </section>

        <div className="flex flex-col gap-5">
          <section className="panel-card px-5 py-5">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">Gap tracker</p>
            <h3 className="mt-2 text-lg font-semibold text-[var(--foreground)]">지금 집중해서 볼 개념</h3>
            <div className="mt-4 space-y-3">
              {learningGaps.map((gap) => (
                <article key={gap.title} className="rounded-[20px] border border-[var(--border)] bg-[var(--surface-muted)] px-4 py-4">
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-sm font-semibold text-[var(--foreground)]">{gap.title}</p>
                    <GapBadge severity={gap.severity} />
                  </div>
                  <p className="mt-2 text-sm leading-6 text-[var(--body)]">{gap.description}</p>
                </article>
              ))}
            </div>
          </section>

          <section className="panel-card px-5 py-5">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">Next actions</p>
            <h3 className="mt-2 text-lg font-semibold text-[var(--foreground)]">다음 복습 액션</h3>
            <div className="mt-4 space-y-3">
              {nextActions.map((action) => (
                <Link
                  key={action.title}
                  href={withProfile(action.href, activeProfile.profileId)}
                  className="block rounded-[20px] border border-[var(--border)] bg-[var(--surface-muted)] px-4 py-4 transition hover:border-[var(--border-strong)]"
                >
                  <p className="text-sm font-semibold text-[var(--foreground)]">{action.title}</p>
                  <p className="mt-2 text-sm leading-6 text-[var(--body)]">{action.description}</p>
                </Link>
              ))}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
