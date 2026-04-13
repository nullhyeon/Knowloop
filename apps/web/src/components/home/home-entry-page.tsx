import type { ReactNode } from "react";
import Link from "next/link";

import { withProfile } from "@/lib/demo-data";

const valueCards = [
  {
    title: "근거가 보이는 답변",
    description:
      "강의 자료, 공식 위키, 세션 맥락을 바탕으로 답변하고, 어떤 지식을 참고했는지 바로 확인할 수 있습니다.",
  },
  {
    title: "후보 지식 검토 후 승격",
    description:
      "불확실한 내용은 바로 공식 지식이 되지 않습니다. Candidate로 모은 뒤 교강사 검토를 거쳐 공식 위키로 승격합니다.",
  },
  {
    title: "질문이 학습 기록으로 남음",
    description:
      "학생 질문은 세션으로만 끝나지 않고 learning note, gap tracker, 다음 액션으로 이어져 복습 흐름을 만듭니다.",
  },
] as const;

const workflowSteps = [
  {
    step: "1",
    title: "질문",
    description: "학생이 현재 수업 맥락에서 질문하고, 시스템은 role과 class scope를 함께 해석합니다.",
  },
  {
    step: "2",
    title: "축적",
    description: "질문은 세션으로 저장되고, 필요하면 learning note와 candidate가 함께 생성됩니다.",
  },
  {
    step: "3",
    title: "검토",
    description: "교강사는 반복 질문과 후보 지식을 review inbox에서 확인하고 patch preview를 검토합니다.",
  },
  {
    step: "4",
    title: "승격",
    description: "검토를 통과한 후보만 공식 위키에 반영되어, 다음 질문의 신뢰 가능한 근거가 됩니다.",
  },
  {
    step: "5",
    title: "탐색",
    description: "학생은 Ask와 Learning에서, 교강사는 Insights와 Wiki에서 축적된 지식을 바로 활용합니다.",
  },
] as const;

const entryCards = [
  {
    profileId: "student-minji",
    title: "학생용 샘플 데이터로 시작",
    description:
      "이미 질문 기록과 학습 노트가 쌓여 있는 학생 관점으로 들어가 Ask, Learning, Wiki 흐름을 바로 체험합니다.",
    href: withProfile("/ask", "student-minji"),
    eyebrow: "Student sample",
    bullets: ["Ask에서 실제 질문/근거 흐름 보기", "Learning에서 confusion, next actions 확인", "Wiki로 연결된 공식 개념 복습"],
  },
  {
    profileId: "instructor-park",
    title: "교강사용 샘플 데이터로 시작",
    description:
      "반복 질문과 후보 지식이 이미 쌓여 있는 교강사 관점으로 들어가 Insights, Review, Wiki 흐름을 바로 체험합니다.",
    href: withProfile("/insights", "instructor-park"),
    eyebrow: "Instructor sample",
    bullets: ["Insights에서 반복 confusion 패턴 보기", "Review에서 candidate 승인 흐름 보기", "Wiki 갱신과 source traceability 확인"],
  },
] as const;

const trustSignals = [
  {
    title: "Official wiki first",
    description: "공식 답변은 유지되는 wiki 맥락을 중심으로 구성됩니다.",
  },
  {
    title: "Candidate gate",
    description: "불확실한 지식은 Candidate를 거쳐 검토된 뒤에만 공식 지식으로 승격됩니다.",
  },
  {
    title: "Traceable evidence",
    description: "source refs, session refs, patch preview로 근거와 변경 흔적을 함께 확인할 수 있습니다.",
  },
  {
    title: "Learning continuity",
    description: "학생 질문은 learning note, gap tracker, next actions로 이어져 실제 복습 경로를 만듭니다.",
  },
] as const;

function SectionEyebrow({ children }: { children: ReactNode }) {
  return (
    <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--muted)]">{children}</p>
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
              <p className="text-xs text-[var(--muted)]">교육용 지식 운영 콘솔 데모</p>
            </div>
          </div>

          <Link
            href="/workspace?profile=student-minji"
            className="rounded-full border border-[var(--border)] bg-[var(--surface)] px-4 py-2 text-sm font-semibold text-[var(--body)] transition hover:border-[var(--border-strong)]"
          >
            Workspace 열기
          </Link>
        </header>

        <section className="grid gap-6 lg:grid-cols-[minmax(0,1.1fr)_420px] lg:items-stretch">
          <div className="panel-card flex flex-col justify-between px-6 py-6 md:px-8 md:py-8">
            <div className="space-y-5">
              <SectionEyebrow>Knowledge operations for education</SectionEyebrow>
              <div className="max-w-3xl space-y-4">
                <h1 className="text-[clamp(2.5rem,2.05rem+1.3vw,3.55rem)] font-semibold leading-[1.14] tracking-[-0.05em] text-[var(--foreground)]">
                  질문이 쌓일수록 더 정교해지는
                  <br />
                  수업 지식 운영 시스템
                </h1>
                <p className="max-w-2xl text-[15px] leading-8 text-[var(--body)] md:text-base">
                  Knowloop는 강의 자료, 질문 기록, 후보 지식을 함께 운영하는 교육용 LLM-Wiki 시스템입니다.
                  답변만 제공하는 챗봇이 아니라, 세션을 축적하고 학습 노트와 후보 지식을 만들며, 검토를
                  거쳐 공식 위키를 갱신합니다.
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
                    <p className="mt-2 text-sm leading-7 text-[var(--body)]">{card.description}</p>
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
                    답변과 함께 evidence, runtime, write-back이 같은 화면에 나타납니다.
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
                    후보 지식은 patch preview와 source refs를 보고 승인/병합/보류할 수 있습니다.
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
                단순 AI 챗봇이 아니라 수업 지식이 유지되는 시스템
              </p>
              <ul className="mt-4 space-y-3 text-sm leading-7 text-[var(--body)]">
                <li>• 질문 기록이 세션과 학습 노트로 남습니다.</li>
                <li>• 불확실한 지식은 Candidate를 거쳐 검토됩니다.</li>
                <li>• 공식 위키가 다음 답변의 기준이 됩니다.</li>
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
                심사위원은 아래 흐름을 먼저 이해한 뒤, 학생/교강사 샘플 데이터로 바로 들어가 이미 축적된 결과를
                체험할 수 있습니다.
              </p>
            </div>
            <p className="text-sm font-medium text-[var(--muted)]">질문이 쌓일수록 공식 지식이 더 안정적으로 정리됩니다.</p>
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
                <p className="mt-4 text-base font-semibold text-[var(--foreground)]">{step.title}</p>
                <p className="mt-2 text-sm leading-7 text-[var(--body)]">{step.description}</p>
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
                  <li key={bullet}>• {bullet}</li>
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
                  href={withProfile("/workspace", card.profileId)}
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
                Knowloop는 질문에 대한 답을 바로 제시하는 것에서 끝나지 않습니다. 어떤 근거를 참고했는지, 어떤
                후보 지식이 만들어졌는지, 공식 위키가 어떻게 유지되는지를 같은 제품 안에서 보여줍니다.
              </p>
            </div>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-1">
              {trustSignals.map((signal) => (
                <article
                  key={signal.title}
                  className="rounded-[22px] border border-[var(--border)] bg-[var(--surface-muted)] px-4 py-4"
                >
                  <p className="text-sm font-semibold text-[var(--foreground)]">{signal.title}</p>
                  <p className="mt-2 text-sm leading-7 text-[var(--body)]">{signal.description}</p>
                </article>
              ))}
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}
