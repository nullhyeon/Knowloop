"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  extractAskTopics,
  fetchAskSessionHistory,
  getAskPromptExamples,
  getAskResponseModeOptions,
  submitAskQuery,
  type AskConversationResult,
  type AskResponseMode,
  type AskSessionHistoryItem,
} from "@/lib/ask-console";
import { defaultContextId, getDomainLabel, getRoleLabel, withContext } from "@/lib/workspace-context";

import { AskEvidencePanel } from "@/components/ask/ask-evidence-panel";
import { useContextBootstrap } from "@/components/console/context-bootstrap-provider";
import { ScopeHeader } from "@/components/console/scope-header";

function SessionStateBadge({
  state,
  label,
}: {
  state: AskSessionHistoryItem["state"];
  label: string;
}) {
  const config = {
    "candidate-linked": "bg-[var(--review-soft)] text-[var(--review)]",
    "learning-linked": "bg-[var(--success-soft)] text-[var(--success)]",
    "source-linked": "bg-[var(--primary-soft)] text-[var(--primary)]",
  }[state];

  return (
    <span className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${config}`}>
      {label}
    </span>
  );
}

function PanelHeading({
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
      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">
        {eyebrow}
      </p>
      <h2 className="text-lg font-semibold tracking-[-0.02em] text-[var(--foreground)]">{title}</h2>
      <p className="text-sm leading-7 text-[var(--body)]">{description}</p>
    </div>
  );
}

function AskComposer({
  draft,
  onDraftChange,
  responseMode,
  onResponseModeChange,
  promptExamples,
  modeOptions,
  contextLabel,
  courseLabel,
  classLabel,
  onSubmit,
  submitLoading,
  submitError,
  disabled,
  contextId,
}: {
  draft: string;
  onDraftChange: (value: string) => void;
  responseMode: AskResponseMode;
  onResponseModeChange: (value: AskResponseMode) => void;
  promptExamples: string[];
  modeOptions: ReturnType<typeof getAskResponseModeOptions>;
  contextLabel: string;
  courseLabel: string;
  classLabel: string;
  onSubmit: () => void;
  submitLoading: boolean;
  submitError: string | null;
  disabled: boolean;
  contextId: string;
}) {
  return (
    <div className="rounded-[24px] border border-[var(--border-strong)] bg-[var(--surface-muted)] px-5 py-5">
      <div className="flex items-center justify-between gap-4">
        <div>
          <p className="text-sm font-semibold text-[var(--foreground)]">질문 작성</p>
          <p className="mt-1 text-sm leading-6 text-[var(--muted)]">
            현재 스코프는 {contextLabel}, {courseLabel}, {classLabel}입니다.
          </p>
        </div>
        <span className="rounded-full bg-[var(--primary-soft)] px-3 py-1.5 text-xs font-semibold text-[var(--primary)]">
          Ask console
        </span>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-[minmax(0,1fr)_220px]">
        <label className="block" htmlFor="ask-composer">
          <span className="muted-label">현재 스코프에서 바로 답을 받고, 증거와 write-back까지 확인할 질문</span>
          <textarea
            id="ask-composer"
            value={draft}
            onChange={(event) => onDraftChange(event.target.value)}
            className="mt-2 min-h-36 w-full rounded-[20px] border border-[var(--border-strong)] bg-[var(--surface)] px-4 py-4 text-sm leading-7 text-[var(--body)] outline-none transition focus:border-[var(--primary)] focus:ring-4 focus:ring-[rgba(37,99,235,0.14)]"
            disabled={disabled}
          />
        </label>

        <div className="rounded-[20px] border border-[var(--border)] bg-[var(--surface)] px-4 py-4">
          <label htmlFor="ask-response-mode" className="muted-label">
            응답 모드
          </label>
          <select
            id="ask-response-mode"
            aria-label="응답 모드"
            className="mt-2 w-full rounded-2xl border border-[var(--border)] bg-[var(--surface-muted)] px-3 py-3 text-sm font-medium text-[var(--body)] outline-none"
            value={responseMode}
            onChange={(event) => onResponseModeChange(event.target.value as AskResponseMode)}
            disabled={disabled}
          >
            {modeOptions.map((mode) => (
              <option key={mode.value} value={mode.value}>
                {mode.label}
              </option>
            ))}
          </select>

          <p className="mt-2 text-xs leading-5 text-[var(--muted)]">
            {modeOptions.find((mode) => mode.value === responseMode)?.description}
          </p>

          <p className="mt-4 muted-label">바로 쓰는 예시</p>
          <div className="mt-2 space-y-2">
            {promptExamples.map((example) => (
              <button
                key={example}
                className="w-full rounded-2xl border border-[var(--border)] bg-[var(--surface-muted)] px-3 py-3 text-left text-xs font-medium leading-6 text-[var(--body)]"
                type="button"
                onClick={() => onDraftChange(example)}
                disabled={disabled}
              >
                {example}
              </button>
            ))}
          </div>
        </div>
      </div>

      {submitError ? (
        <div className="mt-4 rounded-[20px] border border-[var(--danger)] bg-[var(--danger-soft)]/45 px-4 py-4 text-sm leading-6 text-[var(--body)]">
          질문을 처리하지 못했습니다. {submitError}
        </div>
      ) : null}

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <button
          className="rounded-2xl bg-[var(--primary)] px-4 py-2.5 text-sm font-semibold text-white transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
          type="button"
          onClick={onSubmit}
          disabled={disabled || submitLoading || !draft.trim()}
        >
          {submitLoading ? "질문 처리 중..." : "질문 보내기"}
        </button>
        <Link
          href={withContext("/wiki", contextId)}
          className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] px-4 py-2.5 text-sm font-semibold text-[var(--body)]"
        >
          관련 wiki 보기
        </Link>
      </div>
    </div>
  );
}

function AskSkeleton() {
  return (
    <div className="grid flex-1 grid-cols-1 gap-5 xl:grid-cols-[280px_minmax(0,1fr)_320px]">
      {Array.from({ length: 3 }).map((_, index) => (
        <div key={index} className="panel-card min-h-[640px] animate-pulse px-5 py-5">
          <div className="h-4 w-28 rounded-full bg-[var(--surface-muted)]" />
          <div className="mt-4 h-4 w-4/5 rounded-full bg-[var(--surface-muted)]" />
          <div className="mt-2 h-4 w-3/5 rounded-full bg-[var(--surface-muted)]" />
          <div className="mt-6 space-y-3">
            <div className="h-24 rounded-[20px] bg-[var(--surface-muted)]" />
            <div className="h-24 rounded-[20px] bg-[var(--surface-muted)]" />
            <div className="h-24 rounded-[20px] bg-[var(--surface-muted)]" />
          </div>
        </div>
      ))}
    </div>
  );
}

function AccessNote({ message }: { message: string }) {
  return (
    <div className="rounded-[20px] border border-dashed border-[var(--border-strong)] bg-[var(--surface-muted)] px-4 py-5 text-sm leading-6 text-[var(--body)]">
      {message}
    </div>
  );
}

export function AskMainLayout() {
  const { activeContext, self, loading: bootstrapLoading, error: bootstrapError } = useContextBootstrap();

  const [draft, setDraft] = useState("");
  const [responseMode, setResponseMode] = useState<AskResponseMode>("teaching");
  const [searchQuery, setSearchQuery] = useState("");
  const [sessionHistory, setSessionHistory] = useState<AskSessionHistoryItem[]>([]);
  const [selectedSessionId, setSelectedSessionId] = useState("");
  const [activeResult, setActiveResult] = useState<AskConversationResult | null>(null);
  const [sessionLoading, setSessionLoading] = useState(false);
  const [sessionError, setSessionError] = useState<string | null>(null);
  const [submitLoading, setSubmitLoading] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const sessionRequestRef = useRef(0);
  const submitRequestRef = useRef(0);

  const role = activeContext?.role ?? "student";
  const promptExamples = useMemo(() => getAskPromptExamples(role), [role]);
  const responseModeOptions = useMemo(() => getAskResponseModeOptions(role), [role]);

  useEffect(() => {
    submitRequestRef.current += 1;
    setDraft(promptExamples[0] ?? "");
    setResponseMode(responseModeOptions[0]?.value ?? "default");
    setActiveResult(null);
    setSubmitError(null);
    setSubmitLoading(false);
    setSearchQuery("");
  }, [promptExamples, responseModeOptions]);

  const loadSessionHistory = useCallback(async (queryOverride?: string) => {
    if (!activeContext) {
      sessionRequestRef.current += 1;
      setSessionHistory([]);
      setSelectedSessionId("");
      setSessionLoading(false);
      setSessionError(null);
      return;
    }

    const requestSequence = sessionRequestRef.current + 1;
    sessionRequestRef.current = requestSequence;
    setSessionLoading(true);
    setSessionError(null);
    setSessionHistory([]);
    setSelectedSessionId("");

    try {
      const effectiveQuery = queryOverride ?? searchQuery;
      const nextHistory = await fetchAskSessionHistory(
        { contextId: activeContext.contextId },
        { query: effectiveQuery, limit: 12 },
      );

      if (requestSequence !== sessionRequestRef.current) {
        return;
      }

      setSessionHistory(nextHistory);
      setSelectedSessionId((current) =>
        nextHistory.some((item) => item.sessionId === current) ? current : nextHistory[0]?.sessionId ?? "",
      );
    } catch (caughtError) {
      if (requestSequence !== sessionRequestRef.current) {
        return;
      }
      const message =
        caughtError instanceof Error ? caughtError.message : "세션 이력을 불러오지 못했습니다.";
      setSessionError(message);
      setSessionHistory([]);
      setSelectedSessionId("");
    } finally {
      if (requestSequence === sessionRequestRef.current) {
        setSessionLoading(false);
      }
    }
  }, [activeContext, searchQuery]);

  useEffect(() => {
    void loadSessionHistory();
  }, [loadSessionHistory]);

  const selectedSession = useMemo(
    () => sessionHistory.find((item) => item.sessionId === selectedSessionId) ?? null,
    [selectedSessionId, sessionHistory],
  );
  const askTopics = useMemo(() => extractAskTopics(sessionHistory), [sessionHistory]);

  async function handleSubmitQuery() {
    if (!activeContext || !draft.trim()) {
      return;
    }

    const requestSequence = submitRequestRef.current + 1;
    submitRequestRef.current = requestSequence;
    setSubmitLoading(true);
    setSubmitError(null);

    try {
      const nextResult = await submitAskQuery(
        { contextId: activeContext.contextId },
        {
          message: draft.trim(),
          responseMode,
          role: activeContext.role,
          allowRawSourceFallback: true,
        },
      );

      if (requestSequence !== submitRequestRef.current) {
        return;
      }

      setActiveResult(nextResult);
      setSelectedSessionId(nextResult.sessionId);
      setDraft("");
      setSearchQuery("");
      await loadSessionHistory("");
    } catch (caughtError) {
      if (requestSequence !== submitRequestRef.current) {
        return;
      }
      const message =
        caughtError instanceof Error ? caughtError.message : "질문 응답을 완료하지 못했습니다.";
      setSubmitError(message);
    } finally {
      if (requestSequence === submitRequestRef.current) {
        setSubmitLoading(false);
      }
    }
  }

  const roleLabel = activeContext ? getRoleLabel(activeContext.role) : "로딩 중";
  const courseLabel = self?.courseLabel ?? activeContext?.courseLabel ?? "과목 로딩 중";
  const classLabel = self?.classLabel ?? activeContext?.classLabel ?? "반 로딩 중";
  const domainLabel = getDomainLabel(self?.domain ?? activeContext?.domain ?? "academic");
  const contextId = activeContext?.contextId ?? defaultContextId;

  return (
    <div className="flex flex-1 flex-col gap-5 pb-6">
      <ScopeHeader
        title="Ask"
        description="질문, 근거, write-back이 한 화면에서 이어지는 학습 콘솔입니다. 일반 채팅처럼 답만 보여주지 않고, 무엇을 참고했고 어떤 기록이 남는지까지 함께 드러냅니다."
        role={roleLabel}
        course={courseLabel}
        classNameLabel={classLabel}
        domain={domainLabel}
      />

      {bootstrapLoading ? (
        <AskSkeleton />
      ) : (
        <div className="grid flex-1 grid-cols-1 gap-5 xl:grid-cols-[280px_minmax(0,1fr)_320px]">
          <aside className="panel-card flex min-h-[640px] flex-col overflow-hidden">
            <div className="border-b border-[var(--border)] px-5 py-5">
              <PanelHeading
                eyebrow="Recent sessions"
                title="최근 세션과 주제 흐름"
                description="같은 수업 맥락에서 이어진 질문을 실제 session history 기준으로 다시 보고, 자주 나온 태그를 기준으로 흐름을 다시 엽니다."
              />
            </div>

            <div className="border-b border-[var(--border)] px-5 py-4">
              <label htmlFor="ask-session-search" className="muted-label">
                세션 탐색
              </label>
              <input
                id="ask-session-search"
                type="search"
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
                placeholder="연쇄법칙, 과제 제출, refund policy처럼 검색"
                className="mt-2 w-full rounded-2xl border border-[var(--border)] bg-[var(--surface-muted)] px-3 py-3 text-sm text-[var(--body)] outline-none focus-visible:border-[var(--primary)] focus-visible:ring-2 focus-visible:ring-[var(--primary-soft)]"
                disabled={!activeContext}
              />
              <p className="mt-2 text-xs leading-5 text-[var(--muted)]">
                검색어가 없으면 `/sessions/recent`, 입력하면 `/sessions/search` 결과를 사용합니다.
              </p>
            </div>

            <div className="border-b border-[var(--border)] px-5 py-4">
              <p className="text-sm font-semibold text-[var(--foreground)]">자주 이어지는 주제</p>
              <div className="mt-3 flex flex-wrap gap-2">
                {askTopics.length ? (
                  askTopics.map((topic) => (
                    <button
                      key={topic}
                      type="button"
                      onClick={() => setSearchQuery(topic)}
                      className="rounded-full border border-[var(--border)] bg-[var(--surface-muted)] px-3 py-1.5 text-xs font-medium text-[var(--body)]"
                    >
                      {topic}
                    </button>
                  ))
                ) : (
                  <span className="rounded-full border border-[var(--border)] bg-[var(--surface-muted)] px-3 py-1.5 text-xs font-medium text-[var(--muted)]">
                    아직 표시할 topic이 없습니다.
                  </span>
                )}
              </div>
            </div>

            <div className="scrollbar-thin flex-1 overflow-y-auto px-4 py-4">
              {sessionLoading ? (
                <div className="space-y-3 animate-pulse">
                  {Array.from({ length: 4 }).map((_, index) => (
                    <div
                      key={index}
                      className="rounded-[20px] border border-[var(--border)] bg-[var(--surface)] px-4 py-4"
                    >
                      <div className="h-4 w-28 rounded-full bg-[var(--surface-muted)]" />
                      <div className="mt-3 h-4 w-full rounded-full bg-[var(--surface-muted)]" />
                      <div className="mt-2 h-4 w-3/4 rounded-full bg-[var(--surface-muted)]" />
                    </div>
                  ))}
                </div>
              ) : bootstrapError ? (
                <AccessNote message={`context bootstrap을 불러오지 못했습니다. ${bootstrapError}`} />
              ) : sessionError ? (
                <AccessNote message={`세션 이력을 현재 role로 불러오지 못했습니다. ${sessionError}`} />
              ) : sessionHistory.length ? (
                <div className="space-y-3">
                  {sessionHistory.map((session) => {
                    const active = session.sessionId === selectedSessionId;
                    return (
                      <button
                        key={session.sessionId}
                        type="button"
                        onClick={() => setSelectedSessionId(session.sessionId)}
                        aria-pressed={active}
                        aria-current={active ? "true" : undefined}
                        className={`w-full rounded-[20px] border px-4 py-4 text-left transition ${
                          active
                            ? "border-[var(--primary)] bg-[var(--primary-soft)]/50"
                            : "border-[var(--border)] bg-[var(--surface)] hover:border-[var(--border-strong)]"
                        }`}
                      >
                        <div className="flex items-center justify-between gap-3">
                          <p className="text-sm font-semibold text-[var(--foreground)]">{session.title}</p>
                          <SessionStateBadge state={session.state} label={session.stateLabel} />
                        </div>
                        <p className="mt-2 text-sm leading-6 text-[var(--body)]">{session.preview}</p>
                        <div className="mt-3 flex flex-wrap items-center gap-2">
                          {session.tags.map((tag) => (
                            <span
                              key={tag}
                              className="rounded-full bg-[var(--surface-muted)] px-2.5 py-1 text-[11px] font-semibold text-[var(--muted)]"
                            >
                              {tag}
                            </span>
                          ))}
                          <span className="text-[11px] font-medium text-[var(--muted)]">
                            {session.createdAt}
                          </span>
                        </div>
                      </button>
                    );
                  })}
                </div>
              ) : (
                <AccessNote message="현재 스코프에는 아직 recent session이 없습니다. 첫 질문을 보내면 이 영역에 세션 흐름이 쌓입니다." />
              )}
            </div>
          </aside>

          <main className="panel-card flex min-h-[640px] flex-col overflow-hidden">
            <div className="border-b border-[var(--border)] px-6 py-5 lg:px-7">
              <PanelHeading
                eyebrow="Ask flow"
                title="현재 수업 맥락에서 질문하기"
                description="실제 `/query/respond` 응답을 기준으로 현재 답변, recent session history, 그리고 우측 evidence/write-back 패널이 함께 갱신됩니다."
              />
            </div>

            <div className="border-b border-[var(--border)] px-6 py-5 lg:px-7">
              <AskComposer
                draft={draft}
                onDraftChange={setDraft}
                responseMode={responseMode}
                onResponseModeChange={setResponseMode}
                promptExamples={promptExamples}
                modeOptions={responseModeOptions}
                contextLabel={activeContext?.label ?? "현재 컨텍스트"}
                courseLabel={courseLabel}
                classLabel={classLabel}
                onSubmit={handleSubmitQuery}
                submitLoading={submitLoading}
                submitError={submitError}
                disabled={!activeContext}
                contextId={contextId}
              />
            </div>

            <div className="flex-1 px-6 py-5 lg:px-7">
              <div className="space-y-5">
                {activeResult ? (
                  <article className="rounded-[24px] border border-[var(--border)] bg-[var(--surface)] px-5 py-5">
                    <div className="flex items-center justify-between gap-4">
                      <div>
                        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">
                          Current answer
                        </p>
                        <h3 className="mt-2 text-xl font-semibold tracking-[-0.02em] text-[var(--foreground)]">
                          {activeResult.answerTitle}
                        </h3>
                      </div>
                      <span className="rounded-full bg-[var(--success-soft)] px-3 py-1.5 text-xs font-semibold text-[var(--success)]">
                        {activeResult.answerBadge}
                      </span>
                    </div>
                    <p className="mt-4 text-[15px] leading-8 text-[var(--body)]">{activeResult.answerSummary}</p>
                    {activeResult.answerDetail ? (
                      <p className="mt-3 whitespace-pre-line text-sm leading-7 text-[var(--muted)]">
                        {activeResult.answerDetail}
                      </p>
                    ) : null}
                    <div className="mt-4 flex flex-wrap gap-2">
                      <span className="rounded-full bg-[var(--surface-muted)] px-2.5 py-1 text-[11px] font-semibold text-[var(--muted)]">
                        질문 · {activeResult.question}
                      </span>
                      <span className="rounded-full bg-[var(--surface-muted)] px-2.5 py-1 text-[11px] font-semibold text-[var(--muted)]">
                        Session · {activeResult.sessionId}
                      </span>
                      <span className="rounded-full bg-[var(--surface-muted)] px-2.5 py-1 text-[11px] font-semibold text-[var(--muted)]">
                        Created · {activeResult.createdAt}
                      </span>
                    </div>
                  </article>
                ) : (
                  <article className="rounded-[24px] border border-dashed border-[var(--border-strong)] bg-[var(--surface-muted)] px-5 py-5">
                    <div className="flex items-center justify-between gap-4">
                      <div>
                        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">
                          Current answer
                        </p>
                        <h3 className="mt-2 text-xl font-semibold tracking-[-0.02em] text-[var(--foreground)]">
                          아직 현재 query 응답이 없습니다.
                        </h3>
                      </div>
                      <span className="rounded-full bg-[var(--surface)] px-3 py-1.5 text-xs font-semibold text-[var(--body)]">
                        Ready
                      </span>
                    </div>
                    <p className="mt-4 text-[15px] leading-8 text-[var(--body)]">
                      질문을 보내면 중앙에는 실제 답변이, 우측에는 answer basis와 write-back 결과가, 좌측에는 방금 생성된 session history가 함께 갱신됩니다.
                    </p>
                    {selectedSession ? (
                      <div className="mt-4 rounded-[20px] border border-[var(--border)] bg-[var(--surface)] px-4 py-4">
                        <p className="text-sm font-semibold text-[var(--foreground)]">지금 다시 보기 좋은 최근 세션</p>
                        <p className="mt-2 text-sm leading-6 text-[var(--body)]">{selectedSession.preview}</p>
                        {selectedSession.detailPreview ? (
                          <p className="mt-2 text-sm leading-6 text-[var(--muted)]">{selectedSession.detailPreview}</p>
                        ) : null}
                      </div>
                    ) : null}
                  </article>
                )}

                <section className="space-y-3">
                  <div className="flex items-center justify-between">
                    <h3 className="text-sm font-semibold text-[var(--foreground)]">이전 대화 맥락</h3>
                    <span className="text-xs font-medium text-[var(--muted)]">
                      {searchQuery.trim() ? "Search results" : "Recent sessions"}
                    </span>
                  </div>
                  {selectedSession ? (
                    <article className="rounded-[20px] border border-[var(--border)] bg-[var(--surface-muted)] px-4 py-4">
                      <div className="flex items-center justify-between gap-3">
                        <p className="text-sm font-semibold text-[var(--foreground)]">{selectedSession.title}</p>
                        <span className="text-[11px] font-semibold text-[var(--muted)]">
                          {selectedSession.createdAt}
                        </span>
                      </div>
                      <p className="mt-2 text-sm leading-6 text-[var(--body)]">{selectedSession.preview}</p>
                      {selectedSession.detailPreview ? (
                        <p className="mt-2 text-sm leading-6 text-[var(--muted)]">
                          {selectedSession.detailPreview}
                        </p>
                      ) : null}
                      <div className="mt-3 flex flex-wrap gap-2">
                        {selectedSession.tags.map((tag) => (
                          <span
                            key={tag}
                            className="rounded-full bg-[var(--surface)] px-2.5 py-1 text-[11px] font-semibold text-[var(--muted)]"
                          >
                            {tag}
                          </span>
                        ))}
                      </div>
                    </article>
                  ) : (
                    <AccessNote message="왼쪽 recent sessions에서 세션을 선택하면, 이 영역에서 미리보기 맥락을 바로 확인할 수 있습니다." />
                  )}
                </section>
              </div>
            </div>
          </main>

          <aside className="panel-card flex min-h-[640px] flex-col overflow-hidden">
            <div className="border-b border-[var(--border)] px-5 py-5">
              <PanelHeading
                eyebrow="Evidence and write-back"
                title="이번 응답이 무엇을 참고했고 무엇을 남겼는지"
                description="answer basis, retrieval refs, runtime state, learning note update, candidate 결과가 실제 query response 계약 기준으로 함께 표시됩니다."
              />
            </div>

            <AskEvidencePanel panelData={activeResult?.panelData ?? null} />
          </aside>
        </div>
      )}
    </div>
  );
}
