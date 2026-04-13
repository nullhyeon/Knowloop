"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";

import {
  getDomainLabel,
  getProfileById,
  getRoleLabel,
  insightPatterns,
  insightPriorityActions,
  insightSummaryCards,
  withProfile,
} from "@/lib/demo-data";

import { ScopeHeader } from "@/components/console/scope-header";

function InsightToneChip({ tone }: { tone: "neutral" | "review" | "warning" | "success" }) {
  const styles = {
    neutral: "bg-[var(--surface-muted)] text-[var(--muted)]",
    review: "bg-[var(--review-soft)] text-[var(--review)]",
    warning: "bg-[var(--warning-soft)] text-[var(--warning)]",
    success: "bg-[var(--success-soft)] text-[var(--success)]",
  }[tone];

  return <span className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${styles}`}>{tone}</span>;
}

function PriorityActionTone({ tone }: { tone: "review" | "primary" | "warning" }) {
  const styles = {
    review: "bg-[var(--review-soft)] text-[var(--review)]",
    primary: "bg-[var(--primary-soft)] text-[var(--primary)]",
    warning: "bg-[var(--warning-soft)] text-[var(--warning)]",
  }[tone];

  return <span className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${styles}`}>{tone}</span>;
}

export function InsightsMainLayout() {
  const searchParams = useSearchParams();
  const activeProfile = getProfileById(searchParams.get("profile"));
  const insightsAllowed = activeProfile.role === "instructor";

  return (
    <div className="flex flex-1 flex-col gap-5 pb-6">
      <ScopeHeader
        title="Insights"
        description="반복 질문, 오개념 패턴, review 우선순위를 한 화면에서 읽고 다음 수업에서 무엇을 보강할지 바로 결정하는 강사용 운영 대시보드입니다."
        role={getRoleLabel(activeProfile.role)}
        course={activeProfile.courseLabel}
        classNameLabel={activeProfile.classLabel}
        domain={getDomainLabel(activeProfile.domain)}
      />

      {!insightsAllowed ? (
        <div className="panel-card flex min-h-[520px] items-center justify-center px-6 py-8">
          <div className="max-w-2xl rounded-[24px] border border-dashed border-[var(--border-strong)] bg-[var(--surface-muted)] px-6 py-7">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">Insights access</p>
            <h2 className="mt-3 text-2xl font-semibold tracking-[-0.02em] text-[var(--foreground)]">이 화면은 강사용 집계 대시보드입니다.</h2>
            <p className="mt-3 text-sm leading-7 text-[var(--body)]">
              학생, 운영자, 검토자는 같은 시스템을 다른 관점으로 보지만, class-level teaching priority를 정리하는 Insights는 instructor에게만 직접 열립니다.
            </p>
          </div>
        </div>
      ) : (
        <>
          <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            {insightSummaryCards.map((card) => (
              <article key={card.label} className="panel-card px-5 py-5">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">{card.label}</p>
                    <p className="mt-3 text-3xl font-semibold tracking-[-0.03em] text-[var(--foreground)]">{card.value}</p>
                  </div>
                  <InsightToneChip tone={card.tone} />
                </div>
                <p className="mt-3 text-sm leading-6 text-[var(--body)]">{card.hint}</p>
              </article>
            ))}
          </section>

          <div className="grid gap-5 xl:grid-cols-[minmax(0,1.05fr)_360px]">
            <section className="flex flex-col gap-5">
              <article className="panel-card px-6 py-5 lg:px-7">
                <div className="space-y-1">
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">Repeated confusion patterns</p>
                  <h2 className="text-lg font-semibold tracking-[-0.02em] text-[var(--foreground)]">지금 다시 설명해야 하는 패턴</h2>
                  <p className="text-sm leading-7 text-[var(--body)]">차트보다 먼저, 어떤 개념을 왜 다시 설명해야 하는지와 그에 연결된 review/wiki surface를 함께 보여줍니다.</p>
                </div>

                <div className="mt-5 space-y-4">
                  {insightPatterns.map((pattern) => (
                    <article key={pattern.patternId} className="rounded-[22px] border border-[var(--border)] bg-[var(--surface)] px-5 py-5">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="text-sm font-semibold text-[var(--foreground)]">{pattern.title}</p>
                          <p className="mt-2 text-sm leading-7 text-[var(--body)]">{pattern.summary}</p>
                        </div>
                        <span className="rounded-full bg-[var(--surface-muted)] px-2.5 py-1 text-[11px] font-semibold text-[var(--muted)]">
                          {pattern.stateLabel}
                        </span>
                      </div>
                      <div className="mt-4 flex flex-wrap items-center gap-2">
                        <span className="rounded-full bg-[var(--surface-muted)] px-2.5 py-1 text-[11px] font-semibold text-[var(--muted)]">
                          {pattern.signal}
                        </span>
                      </div>
                      <Link
                        href={withProfile(pattern.href, activeProfile.profileId)}
                        className="mt-4 inline-flex rounded-2xl border border-[var(--border)] bg-[var(--surface-muted)] px-4 py-2.5 text-sm font-semibold text-[var(--body)] transition hover:border-[var(--border-strong)]"
                      >
                        {pattern.actionLabel}
                      </Link>
                    </article>
                  ))}
                </div>
              </article>

              <article className="panel-card px-6 py-5 lg:px-7">
                <div className="space-y-1">
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">Next class brief</p>
                  <h2 className="text-lg font-semibold tracking-[-0.02em] text-[var(--foreground)]">다음 수업에서 바로 사용할 요약</h2>
                  <p className="text-sm leading-7 text-[var(--body)]">분석 결과를 예쁜 수치가 아니라 실제 강의 운영 문장으로 바꿔 주는 요약 카드입니다.</p>
                </div>

                <div className="mt-5 rounded-[22px] border border-[var(--border)] bg-[var(--surface-muted)] px-5 py-5">
                  <p className="text-sm font-semibold text-[var(--foreground)]">추천 도입 멘트</p>
                  <p className="mt-3 text-[15px] leading-8 text-[var(--body)]">
                    오늘은 계산을 바로 시작하지 말고, 식의 구조를 먼저 읽는 연습부터 하겠습니다. 함수가 다른 함수 안에 들어 있으면 연쇄법칙, 두 함수가 나란히 곱해져 있으면 곱의 미분법을 먼저 떠올리면 됩니다.
                  </p>
                  <div className="mt-4 flex flex-wrap gap-2">
                    <Link
                      href={withProfile("/wiki", activeProfile.profileId)}
                      className="rounded-2xl bg-[var(--primary)] px-4 py-2.5 text-sm font-semibold text-white transition hover:opacity-90"
                    >
                      관련 Wiki 열기
                    </Link>
                    <Link
                      href={withProfile("/ask", activeProfile.profileId)}
                      className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] px-4 py-2.5 text-sm font-semibold text-[var(--body)] transition hover:border-[var(--border-strong)]"
                    >
                      Ask에서 설명 재현
                    </Link>
                  </div>
                </div>
              </article>
            </section>

            <aside className="flex flex-col gap-5">
              <section className="panel-card px-5 py-5">
                <div className="space-y-1">
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">Priority actions</p>
                  <h2 className="text-lg font-semibold tracking-[-0.02em] text-[var(--foreground)]">지금 먼저 해야 할 일</h2>
                  <p className="text-sm leading-7 text-[var(--body)]">가장 먼저 움직이면 효과가 큰 review, wiki, teaching action을 우선순위대로 배치합니다.</p>
                </div>

                <div className="mt-5 space-y-3">
                  {insightPriorityActions.map((action) => (
                    <Link
                      key={action.actionId}
                      href={withProfile(action.href, activeProfile.profileId)}
                      className="block rounded-[22px] border border-[var(--border)] bg-[var(--surface-muted)] px-4 py-4 transition hover:border-[var(--border-strong)]"
                    >
                      <div className="flex items-center justify-between gap-3">
                        <p className="text-sm font-semibold text-[var(--foreground)]">{action.title}</p>
                        <PriorityActionTone tone={action.tone} />
                      </div>
                      <p className="mt-2 text-sm leading-6 text-[var(--body)]">{action.summary}</p>
                      <div className="mt-3 flex flex-wrap gap-2 text-[11px] font-semibold text-[var(--muted)]">
                        <span className="rounded-full bg-[var(--surface)] px-2.5 py-1">owner · {action.owner}</span>
                        <span className="rounded-full bg-[var(--surface)] px-2.5 py-1">next · {action.nextSurface}</span>
                      </div>
                    </Link>
                  ))}
                </div>
              </section>

              <section className="panel-card px-5 py-5">
                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">Decision framing</p>
                <h3 className="mt-2 text-lg font-semibold text-[var(--foreground)]">이 화면이 말해 주는 것</h3>
                <ul className="mt-4 space-y-3 text-sm leading-7 text-[var(--body)]">
                  <li>가장 많이 반복된 confusion은 연쇄법칙/곱의 미분법 구분 문제입니다.</li>
                  <li>가장 먼저 처리할 review는 운영 FAQ candidate와 sync pending candidate입니다.</li>
                  <li>다음 수업에서는 새 차트를 보여주기보다, 구조를 먼저 읽는 짧은 문장을 다시 설명하는 것이 효과적입니다.</li>
                </ul>
              </section>
            </aside>
          </div>
        </>
      )}
    </div>
  );
}
