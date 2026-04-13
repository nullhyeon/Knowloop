import type { ReviewAction, ReviewCandidate, ReviewPatchLine } from "@/lib/demo-data";

function DiffLine({ line }: { line: ReviewPatchLine }) {
  const lineStyles = {
    context: {
      wrapper: "border-[var(--border)] bg-[var(--surface)] text-[var(--body)]",
      marker: "text-[var(--muted)]",
      symbol: " ",
    },
    addition: {
      wrapper: "border-[var(--success)]/20 bg-[var(--success-soft)] text-[var(--success)]",
      marker: "text-[var(--success)]",
      symbol: "+",
    },
    removal: {
      wrapper: "border-[var(--danger)]/20 bg-[var(--danger-soft)] text-[var(--danger)]",
      marker: "text-[var(--danger)]",
      symbol: "-",
    },
  }[line.kind];

  return (
    <div className={`grid grid-cols-[20px_minmax(0,1fr)] gap-3 rounded-[16px] border px-3 py-3 text-sm leading-6 ${lineStyles.wrapper}`}>
      <span className={`font-mono text-xs font-semibold ${lineStyles.marker}`}>{lineStyles.symbol}</span>
      <p>{line.text}</p>
    </div>
  );
}

function ActionButton({ action }: { action: ReviewAction }) {
  const styles = {
    primary: "bg-[var(--review)] text-white hover:opacity-90",
    secondary: "border border-[var(--border)] bg-[var(--surface)] text-[var(--body)] hover:border-[var(--border-strong)]",
    warning: "bg-[var(--warning)] text-white hover:opacity-90",
    danger: "bg-[var(--danger)] text-white hover:opacity-90",
  }[action.tone];

  return (
    <button
      type="button"
      className={`w-full rounded-2xl px-4 py-3 text-left text-sm font-semibold transition ${styles}`}
    >
      <div className="flex items-center justify-between gap-3">
        <span>{action.label}</span>
        <span className="text-[11px] font-medium opacity-80">Action</span>
      </div>
      <p className="mt-2 text-xs font-medium leading-5 opacity-80">{action.hint}</p>
    </button>
  );
}

export function ReviewPatchPreview({ candidate }: { candidate: ReviewCandidate }) {
  const hasActions = candidate.availableActions.length > 0;

  return (
    <div className="scrollbar-thin flex-1 overflow-y-auto px-4 py-4">
      <div className="space-y-3">
        <article className="rounded-[20px] border border-[var(--border)] bg-[var(--surface-muted)] px-4 py-4">
          <p className="text-sm font-semibold text-[var(--foreground)]">Patch preview</p>
          <p className="mt-2 text-sm leading-6 text-[var(--body)]">{candidate.patchPreviewSummary}</p>
          <div className="mt-4 rounded-[18px] border border-[var(--border)] bg-[var(--surface)] px-3 py-3">
            <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--muted)]">Target page</p>
            <p className="mt-1 text-sm font-semibold text-[var(--foreground)]">{candidate.targetPage}</p>
            <p className="mt-1 text-xs leading-5 text-[var(--muted)]">{candidate.scopeLabel}</p>
          </div>
        </article>

        <article className="rounded-[20px] border border-[var(--border)] bg-[var(--surface)] px-4 py-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-sm font-semibold text-[var(--foreground)]">지식 diff</p>
              <p className="mt-1 text-sm leading-6 text-[var(--body)]">코드 diff가 아니라 공식 문서에 어떤 지식이 추가되거나 교체되는지 읽는 패널입니다.</p>
            </div>
            <span className="rounded-full bg-[var(--review-soft)] px-2.5 py-1 text-[11px] font-semibold text-[var(--review)]">Review</span>
          </div>
          <div className="mt-4 space-y-3">
            {candidate.patchLines.map((line) => (
              <DiffLine key={line.lineId} line={line} />
            ))}
          </div>
        </article>

        <article className="rounded-[20px] border border-[var(--border)] bg-[var(--surface)] px-4 py-4">
          <p className="text-sm font-semibold text-[var(--foreground)]">결정 액션</p>
          <p className="mt-2 text-sm leading-6 text-[var(--body)]">
            {hasActions
              ? "patch preview와 근거를 확인한 뒤, deliberate action으로 candidate lifecycle을 이동시킵니다."
              : "현재 역할은 이 후보를 읽기 전용으로만 확인할 수 있습니다. patch preview와 근거는 볼 수 있지만 최종 결정은 권한이 있는 reviewer가 수행합니다."}
          </p>
          {hasActions ? (
            <div className="mt-4 space-y-3">
              {candidate.availableActions.map((action) => (
                <ActionButton key={action.action} action={action} />
              ))}
            </div>
          ) : (
            <div className="mt-4 rounded-[18px] border border-dashed border-[var(--border-strong)] bg-[var(--surface-muted)] px-4 py-4 text-sm leading-6 text-[var(--body)]">
              이 스코프에서는 patch preview 확인까지만 가능합니다. 필요한 경우 validator 또는 담당 instructor가 approve / merge / drop / resume-sync를 진행합니다.
            </div>
          )}
        </article>
      </div>
    </div>
  );
}

