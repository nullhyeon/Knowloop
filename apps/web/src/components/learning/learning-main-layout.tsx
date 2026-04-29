"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useContextBootstrap } from "@/components/console/context-bootstrap-provider";
import { ScopeHeader } from "@/components/console/scope-header";
import {
  fetchLearningOverview,
  type LearningGapSeverity,
  type LearningOverview,
  type LearningSummaryTone,
} from "@/lib/learning-browser";

function appendContextToHref(href: string, contextId: string): string {
  const separator = href.includes("?") ? "&" : "?";
  return `${href}${separator}context=${encodeURIComponent(contextId)}`;
}

function formatRoleLabel(role: string): string {
  switch (role) {
    case "student":
      return "학생";
    case "instructor":
      return "교강사";
    case "operator":
      return "운영자";
    case "validator":
      return "검토자";
    default:
      return role;
  }
}

function formatDomainLabel(domain: string): string {
  switch (domain) {
    case "academic":
      return "수업";
    case "operations":
      return "운영";
    case "review":
      return "검토";
    default:
      return domain;
  }
}

function SummaryToneBadge({ tone, label }: { tone: LearningSummaryTone; label: string }) {
  const styles = {
    primary: "bg-[var(--primary-soft)] text-[var(--primary)]",
    review: "bg-[var(--review-soft)] text-[var(--review)]",
    success: "bg-[var(--success-soft)] text-[var(--success)]",
    warning: "bg-[var(--warning-soft)] text-[var(--warning)]",
    muted: "bg-[var(--surface-muted)] text-[var(--muted)]",
  }[tone];

  return <span className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${styles}`}>{label}</span>;
}

function GapSeverityBadge({ severity }: { severity: LearningGapSeverity }) {
  const styles = {
    focus: "bg-[var(--review-soft)] text-[var(--review)]",
    watch: "bg-[var(--warning-soft)] text-[var(--warning)]",
    stable: "bg-[var(--success-soft)] text-[var(--success)]",
  }[severity];

  const label = {
    focus: "집중",
    watch: "주의",
    stable: "안정",
  }[severity];

  return <span className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${styles}`}>{label}</span>;
}

function LoadingPanel() {
  return (
    <div className="space-y-5 pb-6">
      <div className="panel-card px-6 py-5 lg:px-7">
        <div className="animate-pulse space-y-4">
          <div className="h-4 w-28 rounded-full bg-[var(--surface-muted)]" />
          <div className="h-9 w-2/3 rounded-full bg-[var(--surface-muted)]" />
          <div className="h-5 w-full rounded-full bg-[var(--surface-muted)]" />
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }).map((_, index) => (
          <div key={index} className="panel-card animate-pulse px-5 py-5">
            <div className="h-3 w-24 rounded-full bg-[var(--surface-muted)]" />
            <div className="mt-4 h-8 w-20 rounded-full bg-[var(--surface-muted)]" />
            <div className="mt-3 h-4 w-full rounded-full bg-[var(--surface-muted)]" />
          </div>
        ))}
      </div>
    </div>
  );
}

function NoticePanel({
  eyebrow,
  title,
  description,
  actionLabel,
  actionHref,
}: {
  eyebrow: string;
  title: string;
  description: string;
  actionLabel?: string;
  actionHref?: string;
}) {
  return (
    <div className="panel-card flex min-h-[420px] items-center justify-center px-6 py-8">
      <div className="max-w-2xl rounded-[24px] border border-dashed border-[var(--border-strong)] bg-[var(--surface-muted)] px-6 py-7">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">{eyebrow}</p>
        <h2 className="mt-3 text-2xl font-semibold tracking-[-0.02em] text-[var(--foreground)]">{title}</h2>
        <p className="mt-3 text-sm leading-7 text-[var(--body)]">{description}</p>
        {actionLabel && actionHref ? (
          <Link
            href={actionHref}
            className="mt-5 inline-flex rounded-2xl bg-[var(--primary)] px-4 py-2.5 text-sm font-semibold text-white transition hover:opacity-90"
          >
            {actionLabel}
          </Link>
        ) : null}
      </div>
    </div>
  );
}

function EmptyState({ title, description }: { title: string; description: string }) {
  return (
    <div className="rounded-[22px] border border-dashed border-[var(--border-strong)] bg-[var(--surface-muted)] px-5 py-5">
      <p className="text-sm font-semibold text-[var(--foreground)]">{title}</p>
      <p className="mt-2 text-sm leading-7 text-[var(--body)]">{description}</p>
    </div>
  );
}

function SectionHeader({
  eyebrow,
  title,
  description,
}: {
  eyebrow: string;
  title: string;
  description: string;
}) {
  return (
    <div className="space-y-1">
      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">{eyebrow}</p>
      <h2 className="text-lg font-semibold tracking-[-0.02em] text-[var(--foreground)]">{title}</h2>
      <p className="text-sm leading-7 text-[var(--body)]">{description}</p>
    </div>
  );
}

export function LearningMainLayout() {
  const { activeContext, loading: bootstrapLoading, error: bootstrapError } = useContextBootstrap();
  const learningAllowed = activeContext?.role === "student";

  const [overview, setOverview] = useState<LearningOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const requestRef = useRef(0);

  const loadLearningOverview = useCallback(async () => {
    if (!activeContext) {
      requestRef.current += 1;
      setOverview(null);
      setLoading(bootstrapLoading);
      setError(null);
      return;
    }

    if (!learningAllowed) {
      requestRef.current += 1;
      setOverview(null);
      setLoading(false);
      setError(null);
      return;
    }

    const requestId = requestRef.current + 1;
    requestRef.current = requestId;
    setLoading(true);
    setError(null);

    try {
      const nextOverview = await fetchLearningOverview({ contextId: activeContext.contextId });
      if (requestId !== requestRef.current) {
        return;
      }
      setOverview(nextOverview);
    } catch (caughtError) {
      if (requestId !== requestRef.current) {
        return;
      }
      const message =
        caughtError instanceof Error ? caughtError.message : "학습 허브 데이터를 불러오지 못했습니다.";
      setError(message);
      setOverview(null);
    } finally {
      if (requestId === requestRef.current) {
        setLoading(false);
      }
    }
  }, [activeContext, bootstrapLoading, learningAllowed]);

  useEffect(() => {
    void loadLearningOverview();
  }, [loadLearningOverview]);

  const summaryCards = useMemo(() => overview?.summaryCards ?? [], [overview]);
  const confusionSignals = useMemo(() => overview?.confusionSignals ?? [], [overview]);
  const recentNotes = useMemo(() => overview?.recentNotes ?? [], [overview]);
  const gaps = useMemo(() => overview?.gaps ?? [], [overview]);
  const nextActions = useMemo(() => overview?.nextActions ?? [], [overview]);
  const wikiLinks = useMemo(() => overview?.wikiLinks ?? [], [overview]);
  const recentSessions = useMemo(() => overview?.recentSessions ?? [], [overview]);

  const hasContent =
    confusionSignals.length > 0 ||
    recentNotes.length > 0 ||
    gaps.length > 0 ||
    nextActions.length > 0 ||
    wikiLinks.length > 0 ||
    recentSessions.length > 0;

  if (bootstrapLoading || (activeContext && loading && !overview && !error)) {
    return <LoadingPanel />;
  }

  if (bootstrapError) {
    return (
      <NoticePanel
        eyebrow="Context bootstrap"
        title="공용 수업 컨텍스트를 불러오지 못했습니다."
        description={bootstrapError}
        actionLabel="Workspace로 이동"
        actionHref="/workspace"
      />
    );
  }

  if (!activeContext) {
    return (
      <NoticePanel
        eyebrow="Learning access"
        title="현재 학습 허브를 열 수 있는 컨텍스트가 없습니다."
        description="컨텍스트 bootstrap이 아직 준비되지 않았습니다. 잠시 후 다시 시도해 주세요."
        actionLabel="Workspace로 이동"
        actionHref="/workspace"
      />
    );
  }

  if (!learningAllowed) {
    return (
      <NoticePanel
        eyebrow="Role guard"
        title="이 화면은 학생 개인 학습 허브입니다."
        description={`${formatRoleLabel(activeContext.role)} 역할에서는 개인 학습 데이터를 직접 열 수 없습니다. Ask, Review, Insights 같은 역할별 화면으로 이어서 확인해 주세요.`}
        actionLabel={`${formatRoleLabel(activeContext.role)} 화면으로 이동`}
        actionHref={appendContextToHref(activeContext.landingSurface || "/workspace", activeContext.contextId)}
      />
    );
  }

  if (error) {
    return (
      <NoticePanel
        eyebrow="Learning data"
        title="학습 허브 데이터를 불러오지 못했습니다."
        description={error}
        actionLabel="다시 시도하기"
        actionHref={appendContextToHref("/learning", activeContext.contextId)}
      />
    );
  }

  const pageSummary = overview?.pageSummary ?? {
    eyebrow: "학습 허브",
    title: "지금 다시 볼 개념과 다음 액션을 정리해 두었습니다.",
    description:
      "질문에서 생긴 혼동 신호, 개인 학습 노트, 다음 복습 액션을 한 화면에서 이어 보며 학습 흐름을 유지합니다.",
    badge: "학생 전용",
  };

  const scopeDescription =
    overview?.scope.description ??
    "질문에서 쌓인 학습 단서를 다시 읽고, 관련 위키와 다음 액션으로 바로 이어지는 개인 학습 콘솔입니다.";

  return (
    <div className="flex flex-1 flex-col gap-5 pb-6">
      <ScopeHeader
        title="Learning"
        description={scopeDescription}
        role={activeContext.label ?? formatRoleLabel(activeContext.role)}
        course={activeContext.courseLabel}
        classNameLabel={activeContext.classLabel}
        domain={formatDomainLabel(activeContext.domain)}
      />

      <section className="panel-card flex items-center justify-between gap-4 px-6 py-5 lg:px-7">
        <div className="max-w-3xl space-y-2">
          <p className="muted-label">{pageSummary.eyebrow}</p>
          <h2 className="text-2xl font-semibold tracking-[-0.02em] text-[var(--foreground)]">{pageSummary.title}</h2>
          <p className="max-w-2xl text-sm leading-7 text-[var(--body)]">{pageSummary.description}</p>
        </div>
        <span className="rounded-full bg-[var(--primary-soft)] px-3 py-1.5 text-xs font-semibold text-[var(--primary)]">
          {pageSummary.badge}
        </span>
      </section>

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {summaryCards.map((card) => (
          <article key={card.label} className="panel-card px-5 py-5">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">{card.label}</p>
                <p className="mt-3 text-3xl font-semibold tracking-[-0.03em] text-[var(--foreground)]">{card.value}</p>
              </div>
              <SummaryToneBadge tone={card.tone} label={card.badge} />
            </div>
            <p className="mt-2 text-sm leading-6 text-[var(--body)]">{card.hint}</p>
          </article>
        ))}
      </section>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.05fr)_360px]">
        <section className="flex flex-col gap-5">
          <article className="panel-card px-6 py-5 lg:px-7">
            <SectionHeader
              eyebrow="Recent confusion"
              title="최근 혼동 신호"
              description="무엇에서 반복적으로 막히는지 먼저 읽고, 바로 아래 학습 노트와 세션으로 이어서 확인할 수 있게 구성했습니다."
            />
            <div className="mt-5 space-y-3">
              {confusionSignals.length > 0 ? (
                confusionSignals.map((signal) => (
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
                    <p className="mt-3 text-[11px] font-semibold text-[var(--muted)]">
                      최근 세션 {signal.sessionCount}건과 연결된 혼동 신호
                    </p>
                  </article>
                ))
              ) : (
                <EmptyState
                  title="아직 기록된 혼동 신호가 없습니다."
                  description="grounded 질문이 쌓이면 반복적으로 막히는 개념이 이 영역에 정리됩니다."
                />
              )}
            </div>
          </article>

          <article className="panel-card px-6 py-5 lg:px-7">
            <SectionHeader
              eyebrow="Learning notes"
              title="최근 학습 노트"
              description="질문에서 파생된 개인 학습 노트를 읽고, 어떤 개념을 중심으로 다시 복습해야 하는지 바로 확인합니다."
            />
            <div className="mt-5 space-y-4">
              {recentNotes.length > 0 ? (
                recentNotes.map((note) => (
                  <article key={note.noteId} className="rounded-[22px] border border-[var(--border)] bg-[var(--surface)] px-5 py-5">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-sm font-semibold text-[var(--foreground)]">{note.title}</p>
                        <p className="mt-2 text-sm leading-7 text-[var(--body)]">{note.summary}</p>
                      </div>
                      <span className="rounded-full bg-[var(--surface-muted)] px-2.5 py-1 text-[11px] font-semibold text-[var(--muted)]">
                        {note.focusLabel}
                      </span>
                    </div>
                    <div className="mt-4 flex flex-wrap gap-2 text-[11px] font-semibold text-[var(--muted)]">
                      <span className="rounded-full bg-[var(--surface-muted)] px-2.5 py-1">세션 · {note.linkedSessionTitle}</span>
                      <span className="rounded-full bg-[var(--surface-muted)] px-2.5 py-1">업데이트 · {note.updatedAt}</span>
                      {note.tags.map((tag) => (
                        <span key={tag} className="rounded-full bg-[var(--surface-muted)] px-2.5 py-1">
                          {tag}
                        </span>
                      ))}
                    </div>
                  </article>
                ))
              ) : (
                <EmptyState
                  title={overview?.emptyState.title ?? "아직 학습 노트가 없습니다."}
                  description={
                    overview?.emptyState.description ??
                    "Ask에서 grounded 질문을 시작하면 learning note와 gap tracker가 이 화면에 쌓입니다."
                  }
                />
              )}
            </div>
          </article>

          <article className="panel-card px-6 py-5 lg:px-7">
            <SectionHeader
              eyebrow="Recent sessions"
              title="최근 질문 기록"
              description="최근에 어떤 질문을 했고, 어떤 답변이 돌아왔는지 빠르게 다시 읽으며 현재 학습 흐름을 잇습니다."
            />
            <div className="mt-5 space-y-3">
              {recentSessions.length > 0 ? (
                recentSessions.map((session) => (
                  <article key={session.sessionId} className="rounded-[20px] border border-[var(--border)] bg-[var(--surface-muted)] px-4 py-4">
                    <div className="flex items-center justify-between gap-3">
                      <p className="text-sm font-semibold text-[var(--foreground)]">{session.title}</p>
                      <span className="rounded-full bg-[var(--surface)] px-2.5 py-1 text-[11px] font-semibold text-[var(--muted)]">
                        {session.stateLabel}
                      </span>
                    </div>
                    <p className="mt-2 text-sm leading-6 text-[var(--body)]">{session.preview}</p>
                    <div className="mt-3 flex flex-wrap items-center gap-2">
                      {session.tags.map((tag) => (
                        <span key={tag} className="rounded-full bg-[var(--surface)] px-2.5 py-1 text-[11px] font-semibold text-[var(--muted)]">
                          {tag}
                        </span>
                      ))}
                      <span className="text-[11px] font-medium text-[var(--muted)]">{session.createdAt}</span>
                    </div>
                  </article>
                ))
              ) : (
                <EmptyState
                  title="최근 질문 기록이 아직 없습니다."
                  description="Ask에서 질문을 시작하면 최근 세션 요약이 이 영역에 연결됩니다."
                />
              )}
            </div>
          </article>
        </section>

        <aside className="flex flex-col gap-5">
          <section className="panel-card px-5 py-5">
            <SectionHeader
              eyebrow="Gap tracker"
              title="지금 다시 볼 개념"
              description="복습 우선순위가 높은 개념을 먼저 읽고, 다음 액션과 위키로 바로 이어집니다."
            />
            <div className="mt-4 space-y-3">
              {gaps.length > 0 ? (
                gaps.map((gap) => (
                  <article key={gap.title} className="rounded-[20px] border border-[var(--border)] bg-[var(--surface-muted)] px-4 py-4">
                    <div className="flex items-center justify-between gap-3">
                      <p className="text-sm font-semibold text-[var(--foreground)]">{gap.title}</p>
                      <GapSeverityBadge severity={gap.severity} />
                    </div>
                    <p className="mt-2 text-sm leading-6 text-[var(--body)]">{gap.description}</p>
                  </article>
                ))
              ) : (
                <EmptyState
                  title="아직 gap tracker가 비어 있습니다."
                  description="질문에서 다시 확인해야 할 개념이 생기면 이 영역에 우선순위가 쌓입니다."
                />
              )}
            </div>
          </section>

          <section className="panel-card px-5 py-5">
            <SectionHeader
              eyebrow="Next actions"
              title="다음 복습 액션"
              description="할 일 목록처럼 끝내지 않고, 어디로 이어서 학습해야 하는지 바로 연결해 둔 액션 카드입니다."
            />
            <div className="mt-4 space-y-3">
              {nextActions.length > 0 ? (
                nextActions.map((action) => (
                  <Link
                    key={action.title}
                    href={action.href ?? appendContextToHref("/ask", activeContext.contextId)}
                    className="block rounded-[20px] border border-[var(--border)] bg-[var(--surface-muted)] px-4 py-4 transition hover:border-[var(--border-strong)]"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <p className="text-sm font-semibold text-[var(--foreground)]">{action.title}</p>
                      <span className="rounded-full bg-[var(--surface)] px-2.5 py-1 text-[11px] font-semibold text-[var(--muted)]">
                        {action.label}
                      </span>
                    </div>
                    <p className="mt-2 text-sm leading-6 text-[var(--body)]">{action.description}</p>
                  </Link>
                ))
              ) : (
                <EmptyState
                  title="아직 다음 액션이 없습니다."
                  description="Ask에서 질문이 쌓이면 복습 경로가 이 영역에 추천됩니다."
                />
              )}
            </div>
          </section>

          <section className="panel-card px-5 py-5">
            <SectionHeader
              eyebrow="Related wiki"
              title="공식 위키로 이어가기"
              description="개인 학습 노트에서 공식 위키로 바로 이어져 안정적으로 다시 복습할 수 있습니다."
            />
            <div className="mt-4 space-y-3">
              {wikiLinks.length > 0 ? (
                wikiLinks.map((item) => (
                  <Link
                    key={item.itemId}
                    href={item.href ?? appendContextToHref("/wiki", activeContext.contextId)}
                    className="block rounded-[20px] border border-[var(--border)] bg-[var(--surface-muted)] px-4 py-4 transition hover:border-[var(--border-strong)]"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <p className="text-sm font-semibold text-[var(--foreground)]">{item.title}</p>
                      <span className="rounded-full bg-[var(--surface)] px-2.5 py-1 text-[11px] font-semibold text-[var(--muted)]">
                        {item.badge}
                      </span>
                    </div>
                    <p className="mt-2 text-sm leading-6 text-[var(--body)]">{item.summary}</p>
                    <p className="mt-3 text-[11px] font-semibold text-[var(--muted)]">{item.reason}</p>
                  </Link>
                ))
              ) : (
                <EmptyState
                  title="연결된 위키가 아직 없습니다."
                  description="관련 개념이 정리되면 공식 위키로 이어지는 링크가 여기에 나타납니다."
                />
              )}
            </div>
          </section>
        </aside>
      </div>

      {!hasContent ? (
        <section className="panel-card px-6 py-5 lg:px-7">
          <div className="max-w-3xl">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">Empty state</p>
            <h2 className="mt-2 text-lg font-semibold text-[var(--foreground)]">아직 축적된 학습 데이터가 없습니다.</h2>
            <p className="mt-2 text-sm leading-7 text-[var(--body)]">
              Ask에서 grounded 질문을 시작하면 세션 기록, learning note, gap tracker, next action이 이 화면에 연결됩니다.
            </p>
          </div>
        </section>
      ) : null}
    </div>
  );
}
