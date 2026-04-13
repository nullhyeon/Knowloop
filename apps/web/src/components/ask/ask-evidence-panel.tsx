import Link from "next/link";

import type { AskEvidenceItem, AskPanelData } from "@/lib/ask-console";

function ToneBadge({ tone }: { tone: AskEvidenceItem["tone"] }) {
  const config = {
    grounded: {
      label: "Grounded",
      className: "bg-[var(--evidence-soft)] text-[var(--evidence)]",
    },
    supporting: {
      label: "Supporting",
      className: "bg-[var(--primary-soft)] text-[var(--primary)]",
    },
    fallback: {
      label: "Fallback",
      className: "bg-[var(--warning-soft)] text-[var(--warning)]",
    },
  }[tone];

  return (
    <span className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${config.className}`}>
      {config.label}
    </span>
  );
}

function ObjectTypeBadge({ objectType }: { objectType: AskEvidenceItem["objectType"] }) {
  return (
    <span className="rounded-full border border-[var(--border)] bg-[var(--surface)] px-2.5 py-1 text-[11px] font-semibold text-[var(--body)]">
      {objectType}
    </span>
  );
}

function SectionTitle({
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
      <h3 className="text-sm font-semibold text-[var(--foreground)]">{title}</h3>
      <p className="text-sm leading-6 text-[var(--body)]">{description}</p>
    </div>
  );
}

function EmptyInlineState({ message }: { message: string }) {
  return (
    <div className="rounded-[18px] border border-dashed border-[var(--border-strong)] bg-[var(--surface-muted)] px-3 py-3 text-sm leading-6 text-[var(--body)]">
      {message}
    </div>
  );
}

export function AskEvidencePanel({ panelData }: { panelData: AskPanelData | null }) {
  if (!panelData) {
    return (
      <div className="flex flex-1 items-center px-4 py-5">
        <div className="rounded-[20px] border border-dashed border-[var(--border-strong)] bg-[var(--surface-muted)] px-4 py-5 text-sm leading-6 text-[var(--body)]">
          아직 query 응답이 없어 evidence와 write-back 패널도 비어 있습니다. 질문을 보내면 formal wiki, session, raw source, learning update가 이 패널에서 바로 보입니다.
        </div>
      </div>
    );
  }

  return (
    <div className="scrollbar-thin flex-1 overflow-y-auto px-4 py-4">
      <div className="space-y-3">
        <article className="rounded-[20px] border border-[var(--border)] bg-[var(--surface-muted)] px-4 py-4">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-sm font-semibold text-[var(--foreground)]">{panelData.answerBasis.title}</p>
              <p className="mt-2 text-sm leading-6 text-[var(--body)]">{panelData.answerBasis.summary}</p>
            </div>
            <span className="rounded-full bg-[var(--evidence-soft)] px-2.5 py-1 text-[11px] font-semibold text-[var(--evidence)]">
              {panelData.answerBasis.stateLabel}
            </span>
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            {panelData.answerBasis.basisTags.map((tag) => (
              <span
                key={tag}
                className="rounded-full bg-[var(--surface)] px-2.5 py-1 text-[11px] font-semibold text-[var(--body)]"
              >
                {tag}
              </span>
            ))}
            <span className="rounded-full bg-[var(--surface)] px-2.5 py-1 text-[11px] font-semibold text-[var(--body)]">
              {panelData.answerBasis.emphasis}
            </span>
          </div>
        </article>

        <article className="rounded-[20px] border border-[var(--border)] bg-[var(--surface)] px-4 py-4">
          <SectionTitle
            eyebrow="Evidence"
            title="참조한 Wiki · Source · Session"
            description="NotebookLM처럼 근거를 바로 읽을 수 있게 두되, Knowloop의 객체 언어와 상태를 함께 보여줍니다."
          />
          <div className="mt-4 space-y-3">
            {panelData.evidenceItems.length ? (
              panelData.evidenceItems.map((item, index) => (
                <div
                  key={item.itemId}
                  className="rounded-[18px] border border-[var(--border)] bg-[var(--surface-muted)] px-3 py-3"
                >
                  <div className="flex items-start gap-3">
                    <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[var(--surface)] text-[11px] font-semibold text-[var(--muted)]">
                      {index + 1}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        {item.href ? (
                          <Link
                            href={item.href}
                            className="text-sm font-semibold text-[var(--foreground)] hover:text-[var(--primary)]"
                          >
                            {item.title}
                          </Link>
                        ) : (
                          <p className="text-sm font-semibold text-[var(--foreground)]">{item.title}</p>
                        )}
                        <ObjectTypeBadge objectType={item.objectType} />
                        <ToneBadge tone={item.tone} />
                      </div>
                      <p className="mt-2 text-sm leading-6 text-[var(--body)]">{item.summary}</p>
                      <p className="mt-2 rounded-2xl border border-[var(--border)] bg-[var(--surface)] px-3 py-3 text-sm leading-6 text-[var(--muted)]">
                        {item.excerpt}
                      </p>
                      <p className="mt-2 text-[11px] font-medium text-[var(--muted)]">{item.meta}</p>
                    </div>
                  </div>
                </div>
              ))
            ) : (
              <EmptyInlineState message="이번 응답은 별도 retrieval ref를 남기지 않았습니다." />
            )}
          </div>
        </article>

        <article className="rounded-[20px] border border-[var(--border)] bg-[var(--surface)] px-4 py-4">
          <SectionTitle
            eyebrow="Runtime"
            title="현재 응답 런타임 상태"
            description="표현은 LLM이 다듬더라도, grounding과 write-back 기준은 시스템 규칙을 따릅니다."
          />
          <div className="mt-4 grid gap-2 sm:grid-cols-2">
            {panelData.runtimeDetails.map((detail) => (
              <div
                key={detail.label}
                className="rounded-[18px] border border-[var(--border)] bg-[var(--surface-muted)] px-3 py-3"
              >
                <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--muted)]">
                  {detail.label}
                </p>
                <p className="mt-2 text-sm font-semibold text-[var(--foreground)]">{detail.value}</p>
              </div>
            ))}
          </div>
        </article>

        <article className="rounded-[20px] border border-[var(--border)] bg-[var(--surface)] px-4 py-4">
          <SectionTitle
            eyebrow="Learning note"
            title={panelData.learningUpdate.title}
            description={panelData.learningUpdate.summary}
          />
          <div className="mt-4 space-y-2">
            {panelData.learningUpdate.highlights.map((highlight) => (
              <div
                key={highlight}
                className="rounded-[18px] border border-[var(--border)] bg-[var(--surface-muted)] px-3 py-3 text-sm leading-6 text-[var(--body)]"
              >
                {highlight}
              </div>
            ))}
          </div>
          <div className="mt-4 flex items-center justify-between gap-3">
            <span className="rounded-full bg-[var(--success-soft)] px-2.5 py-1 text-[11px] font-semibold text-[var(--success)]">
              {panelData.learningUpdate.status}
            </span>
            <Link
              href={panelData.learningUpdate.nextActionHref}
              className="text-sm font-semibold text-[var(--primary)]"
            >
              {panelData.learningUpdate.nextActionLabel}
            </Link>
          </div>
        </article>

        <article className="rounded-[20px] border border-[var(--border)] bg-[var(--surface)] px-4 py-4">
          <SectionTitle
            eyebrow="Candidate"
            title={panelData.candidateOutcome.title}
            description={panelData.candidateOutcome.summary}
          />
          <div className="mt-4 rounded-[18px] border border-[var(--border)] bg-[var(--surface-muted)] px-3 py-3">
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded-full bg-[var(--review-soft)] px-2.5 py-1 text-[11px] font-semibold text-[var(--review)]">
                {panelData.candidateOutcome.status}
              </span>
              <span className="rounded-full bg-[var(--surface)] px-2.5 py-1 text-[11px] font-semibold text-[var(--body)]">
                {panelData.candidateOutcome.targetLabel}
              </span>
            </div>
            <p className="mt-3 text-sm leading-6 text-[var(--body)]">{panelData.candidateOutcome.nextStep}</p>
            {panelData.candidateOutcome.href ? (
              <Link
                href={panelData.candidateOutcome.href}
                className="mt-3 inline-flex text-sm font-semibold text-[var(--primary)]"
              >
                Review에서 열기
              </Link>
            ) : null}
          </div>
        </article>

        <article className="rounded-[20px] border border-[var(--border)] bg-[var(--surface)] px-4 py-4">
          <SectionTitle
            eyebrow="Write-back trail"
            title="질문이 남기는 시스템 흔적"
            description="이번 질문이 세션, 학습 노트, 후보 지식으로 어떻게 이어지는지 순서대로 보여줍니다."
          />
          <div className="mt-4 space-y-3">
            {panelData.writebackTrail.length ? (
              panelData.writebackTrail.map((step, index) => (
                <div key={`${step.objectType}-${index}`} className="flex gap-3">
                  <div className="mt-1 flex flex-col items-center">
                    <span className="flex h-6 w-6 items-center justify-center rounded-full bg-[var(--primary-soft)] text-[11px] font-semibold text-[var(--primary)]">
                      {index + 1}
                    </span>
                    {index < panelData.writebackTrail.length - 1 ? (
                      <span className="mt-2 h-full w-px bg-[var(--border)]" />
                    ) : null}
                  </div>
                  <div className="min-w-0 flex-1 rounded-[18px] border border-[var(--border)] bg-[var(--surface-muted)] px-3 py-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="text-sm font-semibold text-[var(--foreground)]">{step.objectType}</p>
                      <span className="rounded-full bg-[var(--surface)] px-2.5 py-1 text-[11px] font-semibold text-[var(--muted)]">
                        {step.state}
                      </span>
                    </div>
                    <p className="mt-2 text-sm leading-6 text-[var(--body)]">{step.description}</p>
                  </div>
                </div>
              ))
            ) : (
              <EmptyInlineState message="현재 응답에는 남길 write-back 항목이 없습니다." />
            )}
          </div>
        </article>
      </div>
    </div>
  );
}
