"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";

import {
  getDomainLabel,
  getProfileById,
  getRoleLabel,
  learningConfusionSignals,
  learningGaps,
  learningNoteEntries,
  learningSummaryCards,
  learningWikiLinks,
  nextActions,
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
  const learningAllowed = activeProfile.role === "student";

  return (
    <div className="flex flex-1 flex-col gap-5 pb-6">
      <ScopeHeader
        title="Learning"
        description="최근 confusion, 학습 노트, gap tracker, 다음 복습 액션을 한 화면에서 이어서 보는 개인 학습 개입 콘솔입니다. 질문 기록과 공식 위키가 어떻게 복습 흐름으로 연결되는지 보여줍니다."
        role={getRoleLabel(activeProfile.role)}
        course={activeProfile.courseLabel}
        classNameLabel={activeProfile.classLabel}
        domain={getDomainLabel(activeProfile.domain)}
      />

      {!learningAllowed ? (
        <div className="panel-card flex min-h-[520px] items-center justify-center px-6 py-8">
          <div className="max-w-2xl rounded-[24px] border border-dashed border-[var(--border-strong)] bg-[var(--surface-muted)] px-6 py-7">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">Learning access</p>
            <h2 className="mt-3 text-2xl font-semibold tracking-[-0.02em] text-[var(--foreground)]">이 화면은 학생 개인 학습 허브입니다.</h2>
            <p className="mt-3 text-sm leading-7 text-[var(--body)]">
              강사와 검토자는 Ask, Review, Insights에서 class-level 흐름을 보지만, Learning은 학생 질문에서 파생된 개인 학습 개입과 복습 기록을 중심으로 보여줍니다.
            </p>
          </div>
        </div>
      ) : (
        <>
          <section className="grid gap-4 md:grid-cols-3">
            {learningSummaryCards.map((card) => (
              <article key={card.label} className="panel-card px-5 py-5">
                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">{card.label}</p>
                <p className="mt-3 text-3xl font-semibold tracking-[-0.03em] text-[var(--foreground)]">{card.value}</p>
                <p className="mt-2 text-sm leading-6 text-[var(--body)]">{card.hint}</p>
              </article>
            ))}
          </section>

          <div className="grid gap-5 xl:grid-cols-[minmax(0,1.05fr)_360px]">
            <section className="flex flex-col gap-5">
              <article className="panel-card px-6 py-5 lg:px-7">
                <div className="space-y-1">
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">Recent confusion</p>
                  <h2 className="text-lg font-semibold tracking-[-0.02em] text-[var(--foreground)]">지금 다시 봐야 하는 혼동 신호</h2>
                  <p className="text-sm leading-7 text-[var(--body)]">단순 질문 기록이 아니라, 왜 막히고 있는지와 어디로 이어서 복습해야 하는지를 같이 보여주는 영역입니다.</p>
                </div>

                <div className="mt-5 space-y-4">
                  {learningConfusionSignals.map((signal) => (
                    <article key={signal.signalId} className="rounded-[22px] border border-[var(--border)] bg-[var(--surface)] px-5 py-5">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="text-sm font-semibold text-[var(--foreground)]">{signal.title}</p>
                          <p className="mt-2 text-sm leading-7 text-[var(--body)]">{signal.summary}</p>
                        </div>
                        <span className="rounded-full bg-[var(--warning-soft)] px-2.5 py-1 text-[11px] font-semibold text-[var(--warning)]">
                          {signal.stateLabel}
                        </span>
                      </div>
                      <div className="mt-4 flex flex-wrap items-center gap-2">
                        <span className="rounded-full bg-[var(--surface-muted)] px-2.5 py-1 text-[11px] font-semibold text-[var(--muted)]">{signal.frequency}</span>
                      </div>
                      <Link
                        href={withProfile(signal.href, activeProfile.profileId)}
                        className="mt-4 inline-flex rounded-2xl border border-[var(--border)] bg-[var(--surface-muted)] px-4 py-2.5 text-sm font-semibold text-[var(--body)] transition hover:border-[var(--border-strong)]"
                      >
                        관련 surface 열기
                      </Link>
                    </article>
                  ))}
                </div>
              </article>

              <article className="panel-card px-6 py-5 lg:px-7">
                <div className="space-y-1">
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">Learning notes</p>
                  <h2 className="text-lg font-semibold tracking-[-0.02em] text-[var(--foreground)]">질문에서 파생된 학습 노트</h2>
                  <p className="text-sm leading-7 text-[var(--body)]">질문 응답이 끝난 뒤 어떤 학습 문장이 남았는지, 그리고 다음 행동이 무엇인지 바로 이어서 확인할 수 있습니다.</p>
                </div>

                <div className="mt-5 space-y-4">
                  {learningNoteEntries.map((note) => (
                    <article key={note.noteId} className="rounded-[22px] border border-[var(--border)] bg-[var(--surface)] px-5 py-5">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="text-sm font-semibold text-[var(--foreground)]">{note.title}</p>
                          <p className="mt-2 text-sm leading-7 text-[var(--body)]">{note.summary}</p>
                        </div>
                        <span className="rounded-full bg-[var(--primary-soft)] px-2.5 py-1 text-[11px] font-semibold text-[var(--primary)]">
                          {note.focusLabel}
                        </span>
                      </div>
                      <div className="mt-4 flex flex-wrap gap-2 text-[11px] font-semibold text-[var(--muted)]">
                        <span className="rounded-full bg-[var(--surface-muted)] px-2.5 py-1">session · {note.linkedSessionTitle}</span>
                        <span className="rounded-full bg-[var(--surface-muted)] px-2.5 py-1">updated · {note.updatedAt}</span>
                      </div>
                      <Link
                        href={withProfile(note.nextActionHref, activeProfile.profileId)}
                        className="mt-4 inline-flex rounded-2xl border border-[var(--border)] bg-[var(--surface-muted)] px-4 py-2.5 text-sm font-semibold text-[var(--body)] transition hover:border-[var(--border-strong)]"
                      >
                        {note.nextActionLabel}
                      </Link>
                    </article>
                  ))}
                </div>
              </article>
            </section>

            <aside className="flex flex-col gap-5">
              <section className="panel-card px-5 py-5">
                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">Gap tracker</p>
                <h3 className="mt-2 text-lg font-semibold text-[var(--foreground)]">지금 집중해서 메울 간격</h3>
                <p className="mt-2 text-sm leading-7 text-[var(--body)]">혼동 신호를 gap으로 번역해, 이번 주 학습에서 어디를 먼저 다뤄야 하는지 보여줍니다.</p>
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
                <p className="mt-2 text-sm leading-7 text-[var(--body)]">할 일 체크리스트처럼 보이지 않도록, 왜 이 액션이 필요한지와 어디로 이어지는지를 같이 보여줍니다.</p>
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

              <section className="panel-card px-5 py-5">
                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">Related wiki</p>
                <h3 className="mt-2 text-lg font-semibold text-[var(--foreground)]">공식 위키로 이어서 복습하기</h3>
                <p className="mt-2 text-sm leading-7 text-[var(--body)]">학습 노트에서 바로 공식 지식으로 넘어가 같은 개념을 더 안정적으로 복습할 수 있게 연결합니다.</p>
                <div className="mt-4 space-y-3">
                  {learningWikiLinks.map((item) => (
                    <Link
                      key={item.itemId}
                      href={withProfile(item.href, activeProfile.profileId)}
                      className="block rounded-[20px] border border-[var(--border)] bg-[var(--surface-muted)] px-4 py-4 transition hover:border-[var(--border-strong)]"
                    >
                      <div className="flex items-center justify-between gap-3">
                        <p className="text-sm font-semibold text-[var(--foreground)]">{item.title}</p>
                        <span className="rounded-full bg-[var(--surface)] px-2.5 py-1 text-[11px] font-semibold text-[var(--muted)]">Wiki</span>
                      </div>
                      <p className="mt-2 text-sm leading-6 text-[var(--body)]">{item.summary}</p>
                      <p className="mt-3 text-[11px] font-semibold text-[var(--muted)]">{item.reason}</p>
                    </Link>
                  ))}
                </div>
              </section>
            </aside>
          </div>
        </>
      )}
    </div>
  );
}
