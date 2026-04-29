"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { getDomainLabel, getRoleLabel } from "@/lib/workspace-context";
import {
  fetchInsightsDashboard,
  type InsightPriorityAction,
  type InsightSummaryCard,
  type InsightsDashboardData,
} from "@/lib/insights-browser";

import { useContextBootstrap } from "@/components/console/context-bootstrap-provider";
import { ScopeHeader } from "@/components/console/scope-header";

function InsightToneChip({ tone }: { tone: InsightSummaryCard["tone"] }) {
  const styles = {
    neutral: "bg-[var(--surface-muted)] text-[var(--muted)]",
    review: "bg-[var(--review-soft)] text-[var(--review)]",
    warning: "bg-[var(--warning-soft)] text-[var(--warning)]",
    success: "bg-[var(--success-soft)] text-[var(--success)]",
  }[tone];

  return <span className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${styles}`}>{tone}</span>;
}

function PriorityActionTone({ tone }: { tone: InsightPriorityAction["tone"] }) {
  const styles = {
    review: "bg-[var(--review-soft)] text-[var(--review)]",
    primary: "bg-[var(--primary-soft)] text-[var(--primary)]",
    warning: "bg-[var(--warning-soft)] text-[var(--warning)]",
  }[tone];

  return <span className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${styles}`}>{tone}</span>;
}

function InsightsSkeleton() {
  return (
    <div className="space-y-5 animate-pulse">
      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }).map((_, index) => (
          <article key={index} className="panel-card px-5 py-5">
            <div className="h-4 w-28 rounded-full bg-[var(--surface-muted)]" />
            <div className="mt-4 h-9 w-20 rounded-full bg-[var(--surface-muted)]" />
            <div className="mt-4 h-4 w-full rounded-full bg-[var(--surface-muted)]" />
          </article>
        ))}
      </section>
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.05fr)_360px]">
        <section className="panel-card min-h-[540px] px-6 py-5" />
        <aside className="panel-card min-h-[540px] px-5 py-5" />
      </div>
    </div>
  );
}

function AccessPanel() {
  return (
    <div className="panel-card flex min-h-[520px] items-center justify-center px-6 py-8">
      <div className="max-w-2xl rounded-[24px] border border-dashed border-[var(--border-strong)] bg-[var(--surface-muted)] px-6 py-7">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">Insights access</p>
        <h2 className="mt-3 text-2xl font-semibold tracking-[-0.02em] text-[var(--foreground)]">이 화면은 강사용 집계 대시보드입니다.</h2>
        <p className="mt-3 text-sm leading-7 text-[var(--body)]">
          학생 질문과 학습 기록을 집계해 다음 수업에서 무엇을 다시 설명하고 어떤 후보를 먼저 review해야 하는지 판단하는 instructor 전용 surface입니다.
        </p>
      </div>
    </div>
  );
}

function EmptyPanel() {
  return (
    <div className="panel-card flex min-h-[520px] items-center justify-center px-6 py-8">
      <div className="max-w-2xl rounded-[24px] border border-dashed border-[var(--border-strong)] bg-[var(--surface-muted)] px-6 py-7">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">Not enough activity yet</p>
        <h2 className="mt-3 text-2xl font-semibold tracking-[-0.02em] text-[var(--foreground)]">아직 집계할 학생 활동이 충분하지 않습니다.</h2>
        <p className="mt-3 text-sm leading-7 text-[var(--body)]">
          Ask와 Learning, Review 데이터가 더 쌓이면 이 화면이 반복 confusion과 우선 review 후보를 자동으로 요약해 줍니다.
        </p>
      </div>
    </div>
  );
}

function ErrorPanel({ message }: { message: string }) {
  return (
    <div className="panel-card flex min-h-[520px] items-center justify-center px-6 py-8">
      <div className="max-w-2xl rounded-[24px] border border-dashed border-[var(--danger)] bg-[var(--danger-soft)]/45 px-6 py-7">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">Insights error</p>
        <h2 className="mt-3 text-2xl font-semibold tracking-[-0.02em] text-[var(--foreground)]">강사용 집계를 불러오지 못했습니다.</h2>
        <p className="mt-3 text-sm leading-7 text-[var(--body)]">{message}</p>
      </div>
    </div>
  );
}

export function InsightsMainLayout() {
  const { activeContext, self, loading: bootstrapLoading, error: bootstrapError } = useContextBootstrap();
  const insightsAllowed = activeContext?.role === "instructor";

  const [dashboard, setDashboard] = useState<InsightsDashboardData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestSequenceRef = useRef(0);

  const loadDashboard = useCallback(async () => {
    if (!activeContext || !insightsAllowed) {
      requestSequenceRef.current += 1;
      setDashboard(null);
      setLoading(false);
      setError(null);
      return;
    }

    const requestSequence = requestSequenceRef.current + 1;
    requestSequenceRef.current = requestSequence;
    setLoading(true);
    setError(null);

    try {
      const nextDashboard = await fetchInsightsDashboard({ contextId: activeContext.contextId });
      if (requestSequence !== requestSequenceRef.current) {
        return;
      }
      setDashboard(nextDashboard);
    } catch (caughtError) {
      if (requestSequence !== requestSequenceRef.current) {
        return;
      }
      const message = caughtError instanceof Error ? caughtError.message : "instructor insights를 불러오지 못했습니다.";
      setDashboard(null);
      setError(message);
    } finally {
      if (requestSequence === requestSequenceRef.current) {
        setLoading(false);
      }
    }
  }, [activeContext, insightsAllowed]);

  useEffect(() => {
    void loadDashboard();
  }, [loadDashboard]);

  const roleLabel = activeContext ? getRoleLabel(activeContext.role) : "로딩 중";
  const courseLabel = self?.courseLabel ?? activeContext?.courseLabel ?? "과목 로딩 중";
  const classLabel = self?.classLabel ?? activeContext?.classLabel ?? "반 로딩 중";
  const domainLabel = getDomainLabel(self?.domain ?? activeContext?.domain ?? "academic");
  const contextId = activeContext?.contextId ?? null;

  return (
    <div className="flex flex-1 flex-col gap-5 pb-6">
      <ScopeHeader
        title="Insights"
        description="반복 질문, 오개념 패턴, review 우선순위를 한 화면에서 읽고 다음 수업에서 무엇을 보강할지 바로 결정하는 강사용 운영 대시보드입니다."
        role={roleLabel}
        course={courseLabel}
        classNameLabel={classLabel}
        domain={domainLabel}
      />

      {!insightsAllowed ? (
        <AccessPanel />
      ) : bootstrapLoading || loading ? (
        <InsightsSkeleton />
      ) : bootstrapError ? (
        <ErrorPanel message={bootstrapError} />
      ) : error ? (
        <ErrorPanel message={error} />
      ) : !dashboard ? (
        <ErrorPanel message="집계 결과가 비어 있습니다." />
      ) : dashboard.isEmpty ? (
        <EmptyPanel />
      ) : (
        <>
          <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            {dashboard.summaryCards.map((card) => (
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
                  <p className="text-sm leading-7 text-[var(--body)]">백엔드의 pattern 집계를 그대로 읽되, 다음 수업에서 어떤 설명과 review를 먼저 해야 하는지 action-first 구조로 다시 정리했습니다.</p>
                </div>

                <div className="mt-5 space-y-4">
                  {dashboard.patterns.map((pattern) => (
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
                        href={pattern.href}
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
                  <p className="text-sm leading-7 text-[var(--body)]">overview와 pattern 집계를 바탕으로, 차트보다 먼저 바로 말할 수 있는 강의 문장과 우선순위를 보여줍니다.</p>
                </div>

                <div className="mt-5 rounded-[22px] border border-[var(--border)] bg-[var(--surface-muted)] px-5 py-5">
                  <p className="text-sm font-semibold text-[var(--foreground)]">추천 도입 멘트</p>
                  <p className="mt-3 text-[15px] leading-8 text-[var(--body)]">{dashboard.nextClassBrief}</p>
                  <div className="mt-4 flex flex-wrap gap-2">
                    <Link
                      href={contextId ? `/wiki?context=${contextId}` : "/wiki"}
                      className="rounded-2xl bg-[var(--primary)] px-4 py-2.5 text-sm font-semibold text-white transition hover:opacity-90"
                    >
                      관련 Wiki 열기
                    </Link>
                    <Link
                      href={contextId ? `/ask?context=${contextId}` : "/ask"}
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
                  <p className="text-sm leading-7 text-[var(--body)]">가장 먼저 움직이면 효과가 큰 review와 wiki 후속 액션을 우선순위대로 배치합니다.</p>
                </div>

                <div className="mt-5 space-y-3">
                  {dashboard.priorityActions.map((action) => (
                    <Link
                      key={action.actionId}
                      href={action.href}
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
                  {dashboard.decisionFraming.map((line) => (
                    <li key={line}>{line}</li>
                  ))}
                </ul>

                <div className="mt-5 rounded-[20px] border border-[var(--border)] bg-[var(--surface-muted)] px-4 py-4">
                  <p className="muted-label">Top topics</p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {dashboard.topicHighlights.length ? dashboard.topicHighlights.map((topic) => (
                      <span key={topic} className="rounded-full bg-[var(--surface)] px-2.5 py-1 text-[11px] font-semibold text-[var(--muted)]">{topic}</span>
                    )) : <span className="rounded-full bg-[var(--surface)] px-2.5 py-1 text-[11px] font-semibold text-[var(--muted)]">아직 집계된 topic이 없습니다.</span>}
                  </div>
                </div>

                <div className="mt-4 rounded-[20px] border border-[var(--border)] bg-[var(--surface-muted)] px-4 py-4">
                  <p className="muted-label">Top gap clusters</p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {dashboard.gapHighlights.length ? dashboard.gapHighlights.map((gap) => (
                      <span key={gap} className="rounded-full bg-[var(--surface)] px-2.5 py-1 text-[11px] font-semibold text-[var(--muted)]">{gap}</span>
                    )) : <span className="rounded-full bg-[var(--surface)] px-2.5 py-1 text-[11px] font-semibold text-[var(--muted)]">아직 집계된 gap cluster가 없습니다.</span>}
                  </div>
                </div>
              </section>
            </aside>
          </div>
        </>
      )}
    </div>
  );
}
