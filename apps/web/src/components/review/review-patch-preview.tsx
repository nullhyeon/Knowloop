import {
  getDropReasonLabel,
  getDropReasonOptions,
  type ReviewAction,
  type ReviewActionDraft,
  type ReviewCandidateDetail,
  type ReviewPatchLine,
  type ReviewPatchPreview,
  type ReviewCandidateSummary,
} from "@/lib/review-browser";

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
      <p className="whitespace-pre-wrap break-words">{line.text.length ? line.text : "\u00A0"}</p>
    </div>
  );
}

function ActionButton({
  action,
  active,
  disabled,
  onClick,
}: {
  action: ReviewAction;
  active: boolean;
  disabled?: boolean;
  onClick: () => void;
}) {
  const styles = {
    primary: "bg-[var(--review)] text-white hover:opacity-90",
    secondary: "border border-[var(--border)] bg-[var(--surface)] text-[var(--body)] hover:border-[var(--border-strong)]",
    warning: "bg-[var(--warning)] text-white hover:opacity-90",
    danger: "bg-[var(--danger)] text-white hover:opacity-90",
  }[action.tone];

  return (
    <button
      type="button"
      aria-pressed={active}
      disabled={disabled}
      onClick={onClick}
      className={`w-full rounded-2xl px-4 py-3 text-left text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-60 ${styles} ${
        active ? "ring-2 ring-[var(--foreground)]/10" : ""
      }`}
    >
      <div className="flex items-center justify-between gap-3">
        <span>{action.label}</span>
        <span className="text-[11px] font-medium opacity-80">Action</span>
      </div>
      <p className="mt-2 text-xs font-medium leading-5 opacity-80">{action.hint}</p>
    </button>
  );
}

function PanelMessage({ tone, title, description }: { tone: "neutral" | "error" | "success"; title: string; description: string }) {
  const styles = {
    neutral: "border-[var(--border-strong)] bg-[var(--surface-muted)]",
    error: "border-[var(--danger)] bg-[var(--danger-soft)]/60",
    success: "border-[var(--success)] bg-[var(--success-soft)]/60",
  }[tone];

  return (
    <div className={`rounded-[18px] border px-4 py-4 ${styles}`}>
      <p className="text-sm font-semibold text-[var(--foreground)]">{title}</p>
      <p className="mt-2 text-sm leading-6 text-[var(--body)]">{description}</p>
    </div>
  );
}

function MergeTargetSelect({
  options,
  value,
  onChange,
}: {
  options: ReviewCandidateSummary[];
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="block">
      <span className="muted-label">병합 대상 candidate</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="mt-2 w-full rounded-2xl border border-[var(--border)] bg-[var(--surface-muted)] px-3 py-3 text-sm text-[var(--body)] outline-none focus-visible:border-[var(--primary)] focus-visible:ring-2 focus-visible:ring-[var(--primary-soft)]"
      >
        <option value="">대상 후보를 선택하세요</option>
        {options.map((option) => (
          <option key={option.candidateId} value={option.candidateId}>
            {option.title}
          </option>
        ))}
      </select>
    </label>
  );
}

export function ReviewPatchPreview({
  candidate,
  preview,
  previewLoading,
  previewError,
  selectedAction,
  draft,
  mergeOptions,
  actionLoading,
  actionError,
  actionSuccess,
  onSelectAction,
  onRunPreview,
  onRunAction,
  onDraftChange,
}: {
  candidate: ReviewCandidateDetail;
  preview: ReviewPatchPreview | null;
  previewLoading: boolean;
  previewError: string | null;
  selectedAction: ReviewAction["action"] | null;
  draft: ReviewActionDraft;
  mergeOptions: ReviewCandidateSummary[];
  actionLoading: boolean;
  actionError: string | null;
  actionSuccess: string | null;
  onSelectAction: (action: ReviewAction["action"] | null) => void;
  onRunPreview: () => void;
  onRunAction: () => void;
  onDraftChange: (nextDraft: Partial<ReviewActionDraft>) => void;
}) {
  const hasActions = candidate.availableActions.length > 0;
  const canPreview = candidate.actionKeys.includes("patch_preview");
  const mergeUnavailable = mergeOptions.length === 0;
  const runActionDisabled =
    actionLoading || (selectedAction === "merge" && !draft.mergeTargetCandidateId.trim());

  return (
    <div className="scrollbar-thin flex-1 overflow-y-auto px-4 py-4">
      <div className="space-y-3">
        <article className="rounded-[20px] border border-[var(--border)] bg-[var(--surface-muted)] px-4 py-4">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-sm font-semibold text-[var(--foreground)]">Patch preview</p>
              <p className="mt-2 text-sm leading-6 text-[var(--body)]">
                {preview
                  ? preview.patchPreviewSummary
                  : candidate.lifecycleState === "복구 필요"
                    ? "이 candidate는 이미 승격되었고, 지금 필요한 작업은 중단된 wiki sync를 다시 이어 붙이는 것입니다."
                    : "공식 문서에 어떤 지식 변화가 생기는지 먼저 확인한 뒤 approve / merge / drop을 결정합니다."}
              </p>
            </div>
            {canPreview ? (
              <button
                type="button"
                onClick={onRunPreview}
                disabled={previewLoading}
                className="rounded-full border border-[var(--border)] bg-[var(--surface)] px-3 py-1.5 text-xs font-semibold text-[var(--body)] transition hover:border-[var(--border-strong)] disabled:opacity-60"
              >
                {previewLoading ? "불러오는 중" : "미리보기 새로고침"}
              </button>
            ) : null}
          </div>
          <div className="mt-4 rounded-[18px] border border-[var(--border)] bg-[var(--surface)] px-3 py-3">
            <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--muted)]">Target page</p>
            <p className="mt-1 text-sm font-semibold text-[var(--foreground)]">{preview?.targetPage ?? candidate.targetPage}</p>
            <p className="mt-1 text-xs leading-5 text-[var(--muted)]">
              {(preview?.targetPath ?? draft.targetPath ?? candidate.targetPath) || candidate.scopeLabel}
            </p>
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
            {previewLoading ? (
              <PanelMessage tone="neutral" title="patch preview 생성 중" description="실제 review API에서 wiki patch 초안을 불러오고 있습니다." />
            ) : previewError ? (
              <PanelMessage tone="error" title="patch preview를 불러오지 못했습니다" description={previewError} />
            ) : preview ? (
              <>
                {preview.changePlan.length ? (
                  <div className="rounded-[18px] border border-[var(--border)] bg-[var(--surface-muted)] px-4 py-4">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--muted)]">Change plan</p>
                    <ul className="mt-3 space-y-2 text-sm leading-6 text-[var(--body)]">
                      {preview.changePlan.map((step) => (
                        <li key={step} className="list-disc pl-1 ml-4">
                          {step}
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
                {preview.patchLines.map((line) => (
                  <DiffLine key={line.lineId} line={line} />
                ))}
              </>
            ) : candidate.lifecycleState === "복구 필요" ? (
              <PanelMessage tone="neutral" title="resume-sync 대기 상태" description="이 후보는 이미 승격되어 patch preview 대신 동기화 복구 액션이 우선입니다. right panel의 액션에서 resume sync를 실행하면 됩니다." />
            ) : candidate.hasTargetHint ? (
              <PanelMessage tone="neutral" title="patch preview를 아직 불러오지 않았습니다" description="상단의 미리보기 새로고침을 누르면 실제 review API 기준으로 wiki patch 초안을 가져옵니다." />
            ) : (
              <PanelMessage tone="error" title="대상 페이지 힌트가 아직 없습니다" description="approve 또는 patch preview 전에 target page id 혹은 target path를 입력해야 합니다." />
            )}
          </div>
        </article>

        <article className="rounded-[20px] border border-[var(--border)] bg-[var(--surface)] px-4 py-4">
          <p className="text-sm font-semibold text-[var(--foreground)]">결정 액션</p>
          <p className="mt-2 text-sm leading-6 text-[var(--body)]">
            {hasActions
              ? "실제 review API mutation으로 lifecycle을 이동시키는 deliberate action 영역입니다. 먼저 patch preview를 읽고, 필요한 메모를 남긴 뒤 실행하세요."
              : "현재 역할은 이 후보를 읽기 전용으로만 확인할 수 있습니다. patch preview와 근거는 볼 수 있지만 최종 결정은 권한이 있는 reviewer가 수행합니다."}
          </p>

          {actionSuccess ? <div className="mt-4"><PanelMessage tone="success" title="작업이 반영되었습니다" description={actionSuccess} /></div> : null}
          {actionError ? <div className="mt-4"><PanelMessage tone="error" title="review action이 실패했습니다" description={actionError} /></div> : null}

          {hasActions ? (
            <>
              <div className="mt-4 space-y-3">
                {candidate.availableActions.map((action) => (
                  <ActionButton
                    key={action.action}
                    action={action}
                    active={selectedAction === action.action}
                    disabled={actionLoading || (action.action === "merge" && mergeUnavailable)}
                    onClick={() => {
                      if (action.action === "patch_preview") {
                        onRunPreview();
                        onSelectAction(null);
                        return;
                      }
                      onSelectAction(action.action);
                    }}
                  />
                ))}
              </div>

              {selectedAction ? (
                <div className="mt-4 space-y-4 rounded-[18px] border border-[var(--border)] bg-[var(--surface-muted)] px-4 py-4">
                  {selectedAction === "merge" && mergeUnavailable ? (
                    <PanelMessage
                      tone="error"
                      title="병합 가능한 대상이 아직 없습니다"
                      description="현재 큐에 같은 kind와 domain을 가진 열린 canonical candidate가 없어 merge를 실행할 수 없습니다. 다른 후보가 생기기 전까지는 approve 또는 drop을 검토해 주세요."
                    />
                  ) : null}
                  {(selectedAction === "approve" || selectedAction === "patch_preview") && (
                    <>
                      <label className="block">
                        <span className="muted-label">Target page id</span>
                        <input
                          value={draft.targetPageId}
                          onChange={(event) => onDraftChange({ targetPageId: event.target.value })}
                          placeholder="page-faq-homework-submission"
                          className="mt-2 w-full rounded-2xl border border-[var(--border)] bg-[var(--surface)] px-3 py-3 text-sm text-[var(--body)] outline-none focus-visible:border-[var(--primary)] focus-visible:ring-2 focus-visible:ring-[var(--primary-soft)]"
                        />
                      </label>
                      <label className="block">
                        <span className="muted-label">Target path (optional)</span>
                        <input
                          value={draft.targetPath}
                          onChange={(event) => onDraftChange({ targetPath: event.target.value })}
                          placeholder="data/wiki/faq/class-calculus-1-2026-spring-a/homework-submission.md"
                          className="mt-2 w-full rounded-2xl border border-[var(--border)] bg-[var(--surface)] px-3 py-3 text-sm text-[var(--body)] outline-none focus-visible:border-[var(--primary)] focus-visible:ring-2 focus-visible:ring-[var(--primary-soft)]"
                        />
                      </label>
                    </>
                  )}

                  {selectedAction === "merge" ? (
                    <MergeTargetSelect options={mergeOptions} value={draft.mergeTargetCandidateId} onChange={(value) => onDraftChange({ mergeTargetCandidateId: value })} />
                  ) : null}

                  {selectedAction === "drop" ? (
                    <label className="block">
                      <span className="muted-label">Drop reason</span>
                      <select
                        value={draft.dropReason}
                        onChange={(event) => onDraftChange({ dropReason: event.target.value as ReviewActionDraft["dropReason"] })}
                        className="mt-2 w-full rounded-2xl border border-[var(--border)] bg-[var(--surface)] px-3 py-3 text-sm text-[var(--body)] outline-none focus-visible:border-[var(--primary)] focus-visible:ring-2 focus-visible:ring-[var(--primary-soft)]"
                      >
                        {getDropReasonOptions().map((reason) => (
                          <option key={reason} value={reason}>
                            {getDropReasonLabel(reason)}
                          </option>
                        ))}
                      </select>
                    </label>
                  ) : null}

                  <label className="block">
                    <span className="muted-label">
                      {selectedAction === "approve"
                        ? "Approval notes"
                        : selectedAction === "merge"
                          ? "Merge notes"
                          : selectedAction === "drop"
                            ? "Drop notes"
                            : "Resume notes"}
                    </span>
                    <textarea
                      value={draft.notes}
                      onChange={(event) => onDraftChange({ notes: event.target.value })}
                      rows={4}
                      placeholder="검토 근거와 의사결정을 함께 남겨 두세요."
                      className="mt-2 w-full rounded-2xl border border-[var(--border)] bg-[var(--surface)] px-3 py-3 text-sm leading-6 text-[var(--body)] outline-none focus-visible:border-[var(--primary)] focus-visible:ring-2 focus-visible:ring-[var(--primary-soft)]"
                    />
                  </label>

                  <div className="flex items-center justify-end gap-3">
                    <button
                      type="button"
                      onClick={() => onSelectAction(null)}
                      className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] px-4 py-2 text-sm font-semibold text-[var(--body)] transition hover:border-[var(--border-strong)]"
                    >
                      닫기
                    </button>
                    <button
                      type="button"
                      onClick={onRunAction}
                      disabled={runActionDisabled}
                      className="rounded-2xl bg-[var(--review)] px-4 py-2 text-sm font-semibold text-white transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {actionLoading ? "실행 중" : "실제 review API로 실행"}
                    </button>
                  </div>
                </div>
              ) : null}
            </>
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
