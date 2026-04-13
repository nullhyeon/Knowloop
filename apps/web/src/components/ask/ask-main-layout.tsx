"use client";

import { useState } from "react";
import { useSearchParams } from "next/navigation";

import {
  askTopics,
  getAskPanelData,
  getAskSurface,
  getDomainLabel,
  getProfileById,
  getRoleLabel,
  recentSessions,
  responseModes,
  type AskSurface,
} from "@/lib/demo-data";

import { AskEvidencePanel } from "@/components/ask/ask-evidence-panel";
import { ScopeHeader } from "@/components/console/scope-header";

function SessionStateBadge({
  state,
}: {
  state: "wiki-grounded" | "source-fallback" | "needs-review";
}) {
  const config = {
    "wiki-grounded": {
      label: "Wiki grounded",
      className: "bg-[var(--evidence-soft)] text-[var(--evidence)]",
    },
    "source-fallback": {
      label: "Source fallback",
      className: "bg-[var(--warning-soft)] text-[var(--warning)]",
    },
    "needs-review": {
      label: "Needs review",
      className: "bg-[var(--review-soft)] text-[var(--review)]",
    },
  }[state];

  return (
    <span className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${config.className}`}>
      {config.label}
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
  askSurface,
  profileLabel,
  courseLabel,
  classLabel,
}: {
  askSurface: AskSurface;
  profileLabel: string;
  courseLabel: string;
  classLabel: string;
}) {
  const [draft, setDraft] = useState(askSurface.composerDraft);
  const [responseMode, setResponseMode] = useState("teaching");

  return (
    <div className="rounded-[24px] border border-[var(--border-strong)] bg-[var(--surface-muted)] px-5 py-5">
      <div className="flex items-center justify-between gap-4">
        <div>
          <p className="text-sm font-semibold text-[var(--foreground)]">질문 작성</p>
          <p className="mt-1 text-sm leading-6 text-[var(--muted)]">
            현재 스코프는 {profileLabel}, {courseLabel}, {classLabel}입니다.
          </p>
        </div>
        <span className="rounded-full bg-[var(--primary-soft)] px-3 py-1.5 text-xs font-semibold text-[var(--primary)]">
          Ask console
        </span>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-[minmax(0,1fr)_220px]">
        <label className="block" htmlFor="ask-composer">
          <span className="muted-label">{askSurface.composerLabel}</span>
          <textarea
            id="ask-composer"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            className="mt-2 min-h-36 w-full rounded-[20px] border border-[var(--border-strong)] bg-[var(--surface)] px-4 py-4 text-sm leading-7 text-[var(--body)] outline-none transition focus:border-[var(--primary)] focus:ring-4 focus:ring-[rgba(37,99,235,0.14)]"
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
            onChange={(event) => setResponseMode(event.target.value)}
          >
            {responseModes.map((mode) => (
              <option key={mode.value} value={mode.value}>
                {mode.label}
              </option>
            ))}
          </select>

          <p className="mt-4 muted-label">바로 쓰는 예시</p>
          <div className="mt-2 space-y-2">
            {askSurface.promptExamples.map((example) => (
              <button
                key={example}
                className="w-full rounded-2xl border border-[var(--border)] bg-[var(--surface-muted)] px-3 py-3 text-left text-xs font-medium leading-6 text-[var(--body)]"
                type="button"
                onClick={() => setDraft(example)}
              >
                {example}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <button className="rounded-2xl bg-[var(--primary)] px-4 py-2.5 text-sm font-semibold text-white transition hover:opacity-90">
          질문 보내기
        </button>
        <button className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] px-4 py-2.5 text-sm font-semibold text-[var(--body)]">
          관련 source 보기
        </button>
      </div>
    </div>
  );
}

export function AskMainLayout() {
  const searchParams = useSearchParams();
  const activeProfile = getProfileById(searchParams.get("profile"));
  const askSurface = getAskSurface(activeProfile.profileId);
  const askPanelData = getAskPanelData(activeProfile.profileId);

  return (
    <div className="flex flex-1 flex-col gap-5 pb-6">
      <ScopeHeader
        title="Ask"
        description="질문, 근거, write-back이 한 화면에서 이어지는 학습 콘솔입니다. 일반 채팅처럼 답만 보여주지 않고, 무엇을 참고했고 어떤 기록이 남는지까지 함께 드러냅니다."
        role={getRoleLabel(activeProfile.role)}
        course={activeProfile.courseLabel}
        classNameLabel={activeProfile.classLabel}
        domain={getDomainLabel(activeProfile.domain)}
      />

      <div className="grid flex-1 grid-cols-1 gap-5 xl:grid-cols-[280px_minmax(0,1fr)_320px]">
        <aside className="panel-card flex min-h-[640px] flex-col overflow-hidden">
          <div className="border-b border-[var(--border)] px-5 py-5">
            <PanelHeading
              eyebrow="Recent sessions"
              title="최근 세션과 주제 흐름"
              description="같은 수업 맥락에서 이어진 질문을 빠르게 다시 보고, 자주 나온 개념을 기준으로 대화를 이어갈 수 있는 영역입니다."
            />
          </div>

          <div className="border-b border-[var(--border)] px-5 py-4">
            <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface-muted)] px-4 py-3">
              <p className="text-sm font-medium text-[var(--foreground)]">세션 탐색</p>
              <p className="mt-1 text-sm leading-6 text-[var(--muted)]">
                연쇄법칙, 과제 제출, 적분 예외처럼 최근에 많이 나온 주제를 기준으로 흐름을 다시 엽니다.
              </p>
            </div>
          </div>

          <div className="border-b border-[var(--border)] px-5 py-4">
            <p className="text-sm font-semibold text-[var(--foreground)]">자주 이어지는 주제</p>
            <div className="mt-3 flex flex-wrap gap-2">
              {askTopics.map((topic) => (
                <span
                  key={topic}
                  className="rounded-full border border-[var(--border)] bg-[var(--surface-muted)] px-3 py-1.5 text-xs font-medium text-[var(--body)]"
                >
                  {topic}
                </span>
              ))}
            </div>
          </div>

          <div className="scrollbar-thin flex-1 overflow-y-auto px-4 py-4">
            <div className="space-y-3">
              {recentSessions.map((session) => (
                <article
                  key={session.sessionId}
                  className="rounded-[20px] border border-[var(--border)] bg-[var(--surface)] px-4 py-4"
                >
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-sm font-semibold text-[var(--foreground)]">{session.title}</p>
                    <SessionStateBadge state={session.state} />
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
                    <span className="text-[11px] font-medium text-[var(--muted)]">{session.createdAt}</span>
                  </div>
                </article>
              ))}
            </div>
          </div>
        </aside>

        <main className="panel-card flex min-h-[640px] flex-col overflow-hidden">
          <div className="border-b border-[var(--border)] px-6 py-5 lg:px-7">
            <PanelHeading
              eyebrow="Ask flow"
              title={askSurface.title}
              description={askSurface.description}
            />
          </div>

          <div className="border-b border-[var(--border)] px-6 py-5 lg:px-7">
            <AskComposer
              key={activeProfile.profileId}
              askSurface={askSurface}
              profileLabel={activeProfile.label}
              courseLabel={activeProfile.courseLabel}
              classLabel={activeProfile.classLabel}
            />
          </div>

          <div className="flex-1 px-6 py-5 lg:px-7">
            <div className="space-y-5">
              <article className="rounded-[24px] border border-[var(--border)] bg-[var(--surface)] px-5 py-5">
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">
                      Current answer
                    </p>
                    <h3 className="mt-2 text-xl font-semibold tracking-[-0.02em] text-[var(--foreground)]">
                      {askSurface.answerTitle}
                    </h3>
                  </div>
                  <span className="rounded-full bg-[var(--success-soft)] px-3 py-1.5 text-xs font-semibold text-[var(--success)]">
                    Wiki grounded
                  </span>
                </div>
                <p className="mt-4 text-[15px] leading-8 text-[var(--body)]">{askSurface.answerSummary}</p>
                <p className="mt-3 text-sm leading-7 text-[var(--muted)]">{askSurface.answerDetail}</p>
              </article>

              <section className="space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-[var(--foreground)]">이전 대화 맥락</h3>
                  <span className="text-xs font-medium text-[var(--muted)]">Recent sessions</span>
                </div>
                <div className="space-y-3">
                  {recentSessions.slice(0, 2).map((session) => (
                    <article
                      key={session.sessionId}
                      className="rounded-[20px] border border-[var(--border)] bg-[var(--surface-muted)] px-4 py-4"
                    >
                      <div className="flex items-center justify-between gap-3">
                        <p className="text-sm font-semibold text-[var(--foreground)]">{session.title}</p>
                        <span className="text-[11px] font-semibold text-[var(--muted)]">{session.createdAt}</span>
                      </div>
                      <p className="mt-2 text-sm leading-6 text-[var(--body)]">{session.preview}</p>
                    </article>
                  ))}
                </div>
              </section>
            </div>
          </div>
        </main>

        <aside className="panel-card flex min-h-[640px] flex-col overflow-hidden">
          <div className="border-b border-[var(--border)] px-5 py-5">
            <PanelHeading
              eyebrow="Evidence and write-back"
              title={askSurface.rightPanelTitle}
              description={askSurface.rightPanelDescription}
            />
          </div>

          <AskEvidencePanel panelData={askPanelData} profileId={activeProfile.profileId} />
        </aside>
      </div>
    </div>
  );
}
