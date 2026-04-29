import type { ReactNode } from "react";
import Link from "next/link";

import { withContext } from "@/lib/workspace-context";

const valueCards = [
  {
    title: "근거가 보이는 답변",
    description:
      "강의 자료, 공식 위키, 질문 이력을 함께 보고 무엇을 근거로 설명하는지 바로 확인할 수 있습니다.",
  },
  {
    title: "후보 지식 검토 후 승격",
    description:
      "불확실한 내용은 바로 공식 지식이 되지 않습니다. Candidate를 만들고 검토를 거친 뒤에만 공식 위키로 반영합니다.",
  },
  {
    title: "질문이 학습 기록으로 이어짐",
    description:
      "학생 질문은 세션에서 끝나지 않고 learning note, gap tracker, 다음 액션으로 이어져 복습 흐름을 만듭니다.",
  },
] as const;

const workflowSteps = [
  {
    step: "1",
    title: "질문",
    description:
      "학생은 현재 수업 맥락에서 질문하고, 시스템은 role과 class scope를 함께 해석합니다.",
  },
  {
    step: "2",
    title: "축적",
    description:
      "질문은 세션으로 저장되고 필요하면 learning note와 candidate가 함께 생성됩니다.",
  },
  {
    step: "3",
    title: "검토",
    description:
      "교강사는 반복 질문과 후보 지식을 review inbox에서 확인하고 patch preview를 검토합니다.",
  },
  {
    step: "4",
    title: "승격",
    description:
      "검토를 통과한 후보만 공식 위키에 반영되어 다음 답변의 안정적인 근거가 됩니다.",
  },
  {
    step: "5",
    title: "탐색",
    description:
      "학생은 Ask와 Learning에서, 교강사는 Insights와 Wiki에서 축적된 지식을 바로 확인합니다.",
  },
] as const;

const entryCards = [
  {
    contextId: "student-calculus-a",
    title: "학생 컨텍스트로 시작",
    description:
      "학생 역할과 현재 수업 스코프로 들어가 Ask, Learning, Wiki 흐름을 바로 확인합니다.",
    href: withContext("/ask", "student-calculus-a"),
    eyebrow: "Student context",
    bullets: [
      "Ask에서 실제 질문, 근거, write-back 흐름 보기",
      "Learning에서 confusion, gap, next action 확인",
      "Wiki로 연결된 공식 개념 문서 확인",
    ],
  },
  {
    contextId: "instructor-calculus-a",
    title: "교강사 컨텍스트로 시작",
    description:
      "교강사 역할과 현재 수업 스코프로 들어가 Insights, Review, Wiki 흐름을 바로 확인합니다.",
    href: withContext("/insights", "instructor-calculus-a"),
    eyebrow: "Instructor context",
    bullets: [
      "Insights에서 반복 confusion 패턴 보기",
      "Review에서 candidate 검토와 patch preview 보기",
      "Wiki와 Sources에서 공식 지식과 근거 추적 확인",
    ],
  },
] as const;

const trustSignals = [
  {
    title: "Official wiki first",
    description:
      "공식 답변과 후속 탐색은 검토된 위키를 중심으로 구성됩니다.",
  },
  {
    title: "Candidate gate",
    description:
      "불확실한 내용은 Candidate를 거쳐 검토된 뒤에만 공식 지식으로 승격됩니다.",
  },
  {
    title: "Traceable evidence",
    description:
      "source refs, session refs, patch preview로 근거와 변경 이력을 함께 추적할 수 있습니다.",
  },
  {
    title: "Learning continuity",
    description:
      "학생 질문은 learning note, gap tracker, next actions로 이어져 실제 복습 흐름을 만듭니다.",
  },
] as const;

function SectionEyebrow({ children }: { children: ReactNode }) {
  return (
    <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--muted)]">
      {children}
    </p>
  );
}

export function HomeEntryPage() {
  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_top_left,_rgba(37,99,235,0.10),_transparent_24rem),linear-gradient(180deg,_#f9fafb_0%,_var(--background)_20%,_var(--background)_100%)] text-[var(--foreground)]">
      <div className="mx-auto flex w-full max-w-[1240px] flex-col gap-8 px-5 pb-12 pt-6 md:px-8 lg:px-10">
        <header className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-[var(--foreground)] text-sm font-semibold text-white">
              KL
            </div>
            <div>
              <p className="text-sm font-semibold text-[var(--foreground)]">Knowloop</p>
              <p className="text-xs text-[var(--muted)]">교육용 지식 운영 콘솔</p>
            </div>
          </div>

          <Link
            href="/workspace?context=student-calculus-a"
            className="rounded-full border border-[var(--border)] bg-[var(--surface)] px-4 py-2 text-sm font-semibold text-[var(--body)] transition hover:border-[var(--border-strong)]"
          >
            Workspace 보기
          </Link>
        </header>

        <section className="grid gap-6 lg:grid-cols-[minmax(0,1.1fr)_420px] lg:items-stretch">
          <div className="panel-card flex flex-col justify-between px-6 py-6 md:px-8 md:py-8">
            <div className="space-y-5">
              <SectionEyebrow>Knowledge operations for education</SectionEyebrow>
              <div className="max-w-3xl space-y-4">
                <h1 className="text-[clamp(2.5rem,2.05rem+1.3vw,3.55rem)] font-semibold leading-[1.14] tracking-[-0.05em] text-[var(--foreground)]">
                  질문이 쌓일수록 더 정리되는
                  <br />
                  수업 지식 운영 시스템
                </h1>
                <p className="max-w-2xl text-[15px] leading-8 text-[var(--body)] md:text-base">
                  Knowloop는 강의 자료, 질문 기록, 후보 지식을 함께 운영하는 교육용
                  LLM-Wiki 시스템입니다. 답변만 하는 챗봇이 아니라 세션을 축적하고
                  학습 노트와 후보 지식을 만들며, 검토를 거쳐 공식 위키를 갱신합니다.
                </p>
              </div>

              <div className="flex flex-wrap gap-3">
                {entryCards.map((card) => (
                  <Link
                    key={card.title}
                    href={card.href}
                    className="inline-flex items-center rounded-2xl bg-[var(--primary)] px-5 py-3 text-sm font-semibold text-white transition hover:translate-y-[-1px] hover:shadow-[0_12px_24px_rgba(37,99,235,0.18)]"
                  >
                    {card.title}
                  </Link>
                ))}
              </div>

              <div className="grid gap-3 sm:grid-cols-3">
                {valueCards.map((card) => (
                  <article
                    key={card.title}
                    className="rounded-[22px] border border-[var(--border)] bg-[var(--surface-muted)] px-4 py-4"
                  >
                    <p className="text-sm font-semibold text-[var(--foreground)]">{card.title}</p>
                    <p className="mt-2 text-sm leading-7 text-[var(--body)]">
                      {card.description}
                    </p>
                  </article>
                ))}
              </div>
            </div>
          </div>

          <aside className="grid gap-4">
            <article className="panel-card px-5 py-5">
              <SectionEyebrow>제품 미리보기</SectionEyebrow>
              <h2 className="mt-2 text-lg font-semibold tracking-[-0.02em] text-[var(--foreground)]">
                Ask, Review, Wiki가 하나의 흐름으로 연결됩니다
              </h2>
              <div className="mt-5 space-y-3">
                <div className="rounded-[22px] border border-[var(--border)] bg-[var(--surface-muted)] px-4 py-4">
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-sm font-semibold text-[var(--foreground)]">Ask</p>
                    <span className="rounded-full bg-[var(--evidence-soft)] px-2.5 py-1 text-[11px] font-semibold text-[var(--evidence)]">
                      Wiki grounded
                    </span>
                  </div>
                  <p className="mt-2 text-sm leading-6 text-[var(--body)]">
                    답변과 함께 evidence, runtime, write-back이 같은 화면에 보입니다.
                  </p>
                </div>
                <div className="rounded-[22px] border border-[var(--border)] bg-[var(--surface-muted)] px-4 py-4">
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-sm font-semibold text-[var(--foreground)]">Review</p>
                    <span className="rounded-full bg-[var(--review-soft)] px-2.5 py-1 text-[11px] font-semibold text-[var(--review)]">
                      Candidate
                    </span>
                  </div>
                  <p className="mt-2 text-sm leading-6 text-[var(--body)]">
                    후보 지식을 patch preview와 source refs로 검토하고 승인 여부를 판단합니다.
                  </p>
                </div>
                <div className="rounded-[22px] border border-[var(--border)] bg-[var(--surface-muted)] px-4 py-4">
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-sm font-semibold text-[var(--foreground)]">Wiki</p>
                    <span className="rounded-full bg-[var(--success-soft)] px-2.5 py-1 text-[11px] font-semibold text-[var(--success)]">
                      Synced
                    </span>
                  </div>
                  <p className="mt-2 text-sm leading-6 text-[var(--body)]">
                    공식 위키는 source refs, candidate refs, updated_at을 함께 보여주는 maintained knowledge layer입니다.
                  </p>
                </div>
              </div>
            </article>

            <article className="panel-card px-5 py-5">
              <SectionEyebrow>왜 Knowloop인가</SectionEyebrow>
              <p className="mt-2 text-lg font-semibold tracking-[-0.02em] text-[var(--foreground)]">
                단순 AI 챗봇이 아니라 수업 지식이 운영되는 제품
              </p>
              <ul className="mt-4 space-y-3 text-sm leading-7 text-[var(--body)]">
                <li>질문 기록은 세션과 학습 노트로 이어집니다.</li>
                <li>불확실한 지식은 Candidate를 거쳐 검토됩니다.</li>
                <li>공식 위키가 다음 답변의 기준이 됩니다.</li>
              </ul>
            </article>
          </aside>
        </section>

        <section className="panel-card px-6 py-6 md:px-8 md:py-8">
          <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
            <div className="max-w-2xl">
              <SectionEyebrow>How it works</SectionEyebrow>
              <h2 className="mt-2 text-[clamp(1.65rem,1.4rem+0.6vw,2.2rem)] font-semibold tracking-[-0.04em] text-[var(--foreground)]">
                질문 {"->"} 축적 {"->"} 검토 {"->"} 승격 {"->"} 탐색
              </h2>
              <p className="mt-3 text-sm leading-7 text-[var(--body)]">
                사용자는 아래 흐름을 먼저 이해한 뒤, 역할별 컨텍스트로 들어가 실제 서비스 화면을 확인할 수 있습니다.
              </p>
            </div>
            <p className="text-sm font-medium text-[var(--muted)]">
              질문이 쌓일수록 공식 지식이 더 안정적으로 정리됩니다
            </p>
          </div>

          <div className="mt-6 grid gap-4 xl:grid-cols-5">
            {workflowSteps.map((step) => (
              <article
                key={step.step}
                className="rounded-[24px] border border-[var(--border)] bg-[var(--surface-muted)] px-4 py-4"
              >
                <div className="flex h-9 w-9 items-center justify-center rounded-2xl bg-[var(--surface)] text-sm font-semibold text-[var(--foreground)]">
                  {step.step}
                </div>
                <p className="mt-4 text-base font-semibold text-[var(--foreground)]">
                  {step.title}
                </p>
                <p className="mt-2 text-sm leading-7 text-[var(--body)]">
                  {step.description}
                </p>
              </article>
            ))}
          </div>
        </section>

        <section className="grid gap-5 lg:grid-cols-2">
          {entryCards.map((card) => (
            <article key={card.title} className="panel-card px-6 py-6">
              <SectionEyebrow>{card.eyebrow}</SectionEyebrow>
              <h2 className="mt-2 text-[1.45rem] font-semibold tracking-[-0.03em] text-[var(--foreground)]">
                {card.title}
              </h2>
              <p className="mt-3 text-sm leading-7 text-[var(--body)]">{card.description}</p>
              <ul className="mt-5 space-y-2 text-sm leading-7 text-[var(--body)]">
                {card.bullets.map((bullet) => (
                  <li key={bullet}>- {bullet}</li>
                ))}
              </ul>
              <div className="mt-6 flex flex-wrap gap-3">
                <Link
                  href={card.href}
                  className="inline-flex items-center rounded-2xl bg-[var(--primary)] px-5 py-3 text-sm font-semibold text-white transition hover:translate-y-[-1px] hover:shadow-[0_12px_24px_rgba(37,99,235,0.18)]"
                >
                  {card.title}
                </Link>
                <Link
                  href={withContext("/workspace", card.contextId)}
                  className="inline-flex items-center rounded-2xl border border-[var(--border)] bg-[var(--surface)] px-4 py-3 text-sm font-semibold text-[var(--body)] transition hover:border-[var(--border-strong)]"
                >
                  먼저 Workspace 보기
                </Link>
              </div>
            </article>
          ))}
        </section>

        <section className="panel-card px-6 py-6 md:px-8">
          <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_420px]">
            <div>
              <SectionEyebrow>Trust and quality</SectionEyebrow>
              <h2 className="mt-2 text-[1.65rem] font-semibold tracking-[-0.04em] text-[var(--foreground)]">
                근거, 검토, 유지보수가 같이 보이는 AI 시스템
              </h2>
              <p className="mt-3 max-w-2xl text-sm leading-7 text-[var(--body)]">
                Knowloop는 질문에 대한 답변만 바로 제시하는 데서 끝나지 않습니다. 어떤 근거를 사용했는지,
                어떤 후보 지식이 만들어졌는지, 공식 위키가 어떻게 유지보수되는지를 같은 제품 안에서 함께 보여줍니다.
              </p>
            </div>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-1">
              {trustSignals.map((signal) => (
                <article
                  key={signal.title}
                  className="rounded-[22px] border border-[var(--border)] bg-[var(--surface-muted)] px-4 py-4"
                >
                  <p className="text-sm font-semibold text-[var(--foreground)]">
                    {signal.title}
                  </p>
                  <p className="mt-2 text-sm leading-7 text-[var(--body)]">
                    {signal.description}
                  </p>
                </article>
              ))}
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}
