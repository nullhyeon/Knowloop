"use client";

import Link from "next/link";

import { getDomainLabel, getEntrySuggestionsForContext, getRoleLabel, withContext } from "@/lib/workspace-context";

import { ScopeHeader } from "@/components/console/scope-header";
import { useContextBootstrap } from "@/components/console/context-bootstrap-provider";

function WorkspaceSkeleton() {
  return (
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1.15fr)_360px]">
      <section className="panel-card px-6 py-6 lg:px-7">
        <div className="animate-pulse space-y-4">
          <div className="h-4 w-28 rounded-full bg-[var(--surface-muted)]" />
          <div className="h-8 w-96 max-w-full rounded-full bg-[var(--surface-muted)]" />
          <div className="h-4 w-full rounded-full bg-[var(--surface-muted)]" />
          <div className="grid gap-4 md:grid-cols-2">
            <div className="h-52 rounded-[24px] bg-[var(--surface-muted)]" />
            <div className="h-52 rounded-[24px] bg-[var(--surface-muted)]" />
          </div>
        </div>
      </section>
      <div className="flex flex-col gap-5">
        <section className="panel-card h-64 animate-pulse bg-[var(--surface)]" />
        <section className="panel-card h-56 animate-pulse bg-[var(--surface)]" />
      </div>
    </div>
  );
}

export function WorkspaceOverview() {
  const { contexts, activeContext, self, loading, error, refresh } = useContextBootstrap();
  const recentContexts = getEntrySuggestionsForContext(activeContext?.contextId);

  return (
    <div className="flex flex-1 flex-col gap-5 pb-6">
      <ScopeHeader
        title="Workspace"
        description="현재 어떤 역할과 수업 맥락으로 들어갈지 정하는 진입 화면입니다. 기술적인 헤더 값을 직접 입력하지 않고, 역할 카드와 최근 맥락을 통해 바로 작업을 시작할 수 있어야 합니다."
        role={activeContext ? getRoleLabel(activeContext.role) : "Loading"}
        course={self?.courseLabel ?? activeContext?.courseLabel ?? "context loading"}
        classNameLabel={self?.classLabel ?? activeContext?.classLabel ?? "context loading"}
        domain={getDomainLabel(self?.domain ?? activeContext?.domain ?? "academic")}
      />

      {loading && !contexts.length ? (
        <WorkspaceSkeleton />
      ) : error ? (
        <div className="panel-card flex min-h-[520px] items-center justify-center px-6 py-8">
          <div className="max-w-2xl rounded-[24px] border border-dashed border-[var(--danger)] bg-[var(--danger-soft)]/50 px-6 py-7">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">Entry setup failed</p>
            <h2 className="mt-3 text-2xl font-semibold tracking-[-0.02em] text-[var(--foreground)]">workspace context를 아직 불러오지 못했습니다.</h2>
            <p className="mt-3 text-sm leading-7 text-[var(--body)]">
              워크스페이스 컨텍스트나 canonical context를 읽는 단계에서 문제가 생겼습니다. backend를 다시 확인한 뒤 context bootstrap을 재시도하면 role-aware shell이 실제 응답 기준으로 다시 정렬됩니다.
            </p>
            <button
              type="button"
              onClick={() => void refresh()}
              className="mt-5 rounded-2xl bg-[var(--primary)] px-4 py-2.5 text-sm font-semibold text-white transition hover:opacity-90"
            >
              다시 불러오기
            </button>
          </div>
        </div>
      ) : (
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1.15fr)_360px]">
          <section className="panel-card px-6 py-6 lg:px-7">
            <div className="max-w-3xl space-y-2">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">Role-aware entry</p>
              <h2 className="text-2xl font-semibold tracking-[-0.02em] text-[var(--foreground)]">
                지금 어떤 역할과 수업 맥락으로 Knowloop에 들어갈지 먼저 선택합니다.
              </h2>
              <p className="text-sm leading-7 text-[var(--body)]">
                이제 이 화면은 실제 backend context self 응답과 프론트의 워크스페이스 컨텍스트를 기준으로 동작합니다. 학생은 질문과 학습 기록을, 강사는 반복 질문과 공식 지식 반영을, 검토자는 승격 품질과 maintenance를 중심으로 같은 시스템을 다른 관점에서 보게 됩니다.
              </p>
            </div>

            <div className="mt-6 grid gap-4 md:grid-cols-2">
              {contexts.map((context) => {
                const active = context.contextId === activeContext?.contextId;
                return (
                  <article
                    key={context.contextId}
                    className={`rounded-[24px] border px-5 py-5 transition ${
                      active
                        ? "border-[var(--primary)] bg-[var(--primary-soft)]"
                        : "border-[var(--border)] bg-[var(--surface-muted)]"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-lg font-semibold text-[var(--foreground)]">{context.label}</p>
                        <p className="mt-1 text-sm text-[var(--muted)]">
                          {getRoleLabel(context.role)} · {context.courseLabel} · {context.classLabel}
                        </p>
                      </div>
                      <span className="rounded-full border border-[var(--border)] bg-[var(--surface)] px-2.5 py-1 text-[11px] font-semibold text-[var(--body)]">
                        {getDomainLabel(context.domain)}
                      </span>
                    </div>
                    <p className="mt-4 text-sm leading-6 text-[var(--body)]">{context.description}</p>
                    <div className="mt-5 flex flex-wrap gap-2">
                      <Link
                        href={withContext(context.landingSurface, context.contextId)}
                        className="rounded-2xl bg-[var(--primary)] px-4 py-2.5 text-sm font-semibold text-white transition hover:opacity-90"
                      >
                        이 역할로 시작하기
                      </Link>
                      <Link
                        href={withContext("/workspace", context.contextId)}
                        className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] px-4 py-2.5 text-sm font-semibold text-[var(--body)]"
                      >
                        맥락만 전환하기
                      </Link>
                    </div>
                  </article>
                );
              })}
            </div>
          </section>

          <div className="flex flex-col gap-5">
            <section className="panel-card px-5 py-5">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">Continue where you left off</p>
              <h3 className="mt-2 text-lg font-semibold text-[var(--foreground)]">최근 맥락 이어서 보기</h3>
              {recentContexts.length ? (
                <div className="mt-4 space-y-3">
                  {recentContexts.map((context) => (
                    <Link
                      key={context.contextId}
                      href={withContext(context.href, activeContext?.contextId ?? context.contextId)}
                      className="block rounded-[20px] border border-[var(--border)] bg-[var(--surface-muted)] px-4 py-4 transition hover:border-[var(--border-strong)]"
                    >
                      <div className="flex items-center justify-between gap-3">
                        <p className="text-sm font-semibold text-[var(--foreground)]">{context.title}</p>
                        <span className="rounded-full bg-[var(--surface)] px-2.5 py-1 text-[11px] font-semibold text-[var(--muted)]">{context.badge}</span>
                      </div>
                      <p className="mt-2 text-sm leading-6 text-[var(--body)]">{context.summary}</p>
                    </Link>
                  ))}
                </div>
              ) : (
                <div className="mt-4 rounded-[20px] border border-dashed border-[var(--border-strong)] bg-[var(--surface-muted)] px-4 py-5 text-sm leading-6 text-[var(--body)]">
                  아직 최근 맥락이 없습니다. 위 역할 카드에서 올바른 수업 맥락을 먼저 고르면 다음부터 이 영역에 이어서 보기 흐름이 쌓입니다.
                </div>
              )}
            </section>

            <section className="panel-card px-5 py-5">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">Canonical context</p>
              <h3 className="mt-2 text-lg font-semibold text-[var(--foreground)]">현재 backend가 해석한 실제 컨텍스트</h3>
              <div className="mt-4 space-y-3 text-sm leading-6 text-[var(--body)]">
                <div className="rounded-[20px] border border-[var(--border)] bg-[var(--surface-muted)] px-4 py-4">
                  <p className="font-semibold text-[var(--foreground)]">Role / Actor</p>
                  <p className="mt-1">{activeContext ? `${getRoleLabel(activeContext.role)} · ${self?.actorId ?? activeContext.actorId}` : "loading"}</p>
                </div>
                <div className="rounded-[20px] border border-[var(--border)] bg-[var(--surface-muted)] px-4 py-4">
                  <p className="font-semibold text-[var(--foreground)]">Course / Class</p>
                  <p className="mt-1">{self?.courseLabel ?? activeContext?.courseLabel} · {self?.classLabel ?? activeContext?.classLabel}</p>
                </div>
                <div className="rounded-[20px] border border-[var(--border)] bg-[var(--surface-muted)] px-4 py-4">
                  <p className="font-semibold text-[var(--foreground)]">Domain</p>
                  <p className="mt-1">{getDomainLabel(self?.domain ?? activeContext?.domain ?? "academic")}</p>
                </div>
              </div>
            </section>
          </div>
        </div>
      )}
    </div>
  );
}
