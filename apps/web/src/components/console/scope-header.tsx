type ScopeHeaderProps = {
  title: string;
  description: string;
  role: string;
  course: string;
  classNameLabel: string;
  domain: string;
};

export function ScopeHeader({
  title,
  description,
  role,
  course,
  classNameLabel,
  domain,
}: ScopeHeaderProps) {
  return (
    <header className="panel-card flex flex-col gap-6 px-6 py-5 lg:px-7">
      <div className="flex flex-col gap-3">
        <span className="muted-label">Knowledge operations console</span>
        <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-3xl space-y-2">
            <h1 className="page-title">{title}</h1>
            <p className="max-w-2xl text-sm leading-7 text-[var(--body)] lg:text-[15px]">
              {description}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <span className="scope-chip">{role}</span>
            <span className="scope-chip">{course}</span>
            <span className="scope-chip">{classNameLabel}</span>
            <span className="scope-chip">{domain}</span>
          </div>
        </div>
      </div>
    </header>
  );
}

