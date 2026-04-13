"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import type { ReactNode } from "react";

import { getDomainLabel, getNavigationForRole, getRoleLabel, withProfile } from "@/lib/demo-data";

import { useContextBootstrap } from "@/components/console/context-bootstrap-provider";

type ConsoleShellProps = {
  children: ReactNode;
};

function ShellSkeleton() {
  return (
    <>
      <div className="h-3 w-20 rounded-full bg-[var(--surface-muted)]" />
      <div className="mt-4 space-y-3">
        <div className="h-5 w-36 rounded-full bg-[var(--surface-muted)]" />
        <div className="h-4 w-28 rounded-full bg-[var(--surface-muted)]" />
        <div className="h-12 rounded-[20px] bg-[var(--surface-muted)]" />
      </div>
    </>
  );
}

export function ConsoleShell({ children }: ConsoleShellProps) {
  const pathname = usePathname();
  const router = useRouter();
  const { profiles, activeProfile, self, loading, error, refresh } = useContextBootstrap();
  const visibleNavigationItems = activeProfile ? getNavigationForRole(activeProfile.role) : [];

  function resolveProfileHref(profileId: string) {
    const profile = profiles.find((candidate) => candidate.profileId === profileId);

    if (!profile) {
      return withProfile("/workspace", profileId);
    }

    const canStayOnCurrentPath = getNavigationForRole(profile.role).some(
      (item) => pathname === item.href || pathname.startsWith(`${item.href}/`),
    );
    const targetPath = canStayOnCurrentPath ? pathname : profile.landingSurface;
    return withProfile(targetPath, profile.profileId);
  }

  function handleProfileChange(profileId: string) {
    router.push(resolveProfileHref(profileId));
  }

  return (
    <div className="min-h-screen bg-[var(--background)] text-[var(--foreground)]">
      <div className="mx-auto grid min-h-screen max-w-[1440px] grid-cols-1 gap-5 px-4 py-4 lg:grid-cols-[280px_minmax(0,1fr)] lg:px-5">
        <aside className="panel-card sticky top-4 hidden h-[calc(100vh-2rem)] flex-col overflow-hidden lg:flex">
          <div className="border-b border-[var(--border)] px-5 py-5">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">Knowloop</p>
            {loading && !activeProfile ? (
              <div className="mt-3 animate-pulse">
                <ShellSkeleton />
              </div>
            ) : activeProfile ? (
              <>
                <div className="mt-3 space-y-1">
                  <h2 className="text-lg font-semibold text-[var(--foreground)]">{activeProfile.label}</h2>
                  <p className="text-sm leading-6 text-[var(--muted)]">
                    {getRoleLabel(activeProfile.role)} 워크스페이스 · {activeProfile.classLabel}
                  </p>
                </div>
                <p className="mt-3 text-sm leading-6 text-[var(--body)]">{activeProfile.description}</p>
              </>
            ) : (
              <div className="mt-3 rounded-[20px] border border-dashed border-[var(--border-strong)] bg-[var(--surface-muted)] px-4 py-4 text-sm leading-6 text-[var(--body)]">
                context bootstrap을 아직 불러오지 못했습니다.
              </div>
            )}
          </div>

          <div className="border-b border-[var(--border)] px-5 py-4">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">역할 전환</p>
            {error ? (
              <div className="mt-3 rounded-[20px] border border-dashed border-[var(--danger)] bg-[var(--danger-soft)]/50 px-4 py-4 text-sm leading-6 text-[var(--body)]">
                <p className="font-semibold text-[var(--foreground)]">entry setup failed</p>
                <p className="mt-2">{error}</p>
                <button
                  type="button"
                  onClick={() => void refresh()}
                  className="mt-4 rounded-2xl border border-[var(--border)] bg-[var(--surface)] px-4 py-2.5 text-sm font-semibold text-[var(--body)]"
                >
                  다시 불러오기
                </button>
              </div>
            ) : loading && !profiles.length ? (
              <div className="mt-3 space-y-2 animate-pulse">
                <div className="h-16 rounded-[20px] bg-[var(--surface-muted)]" />
                <div className="h-16 rounded-[20px] bg-[var(--surface-muted)]" />
              </div>
            ) : (
              <div className="mt-3 space-y-2">
                {profiles.map((profile) => {
                  const active = profile.profileId === activeProfile?.profileId;
                  return (
                    <Link
                      key={profile.profileId}
                      href={resolveProfileHref(profile.profileId)}
                      className={`block rounded-2xl border px-3 py-3 transition ${
                        active
                          ? "border-[var(--primary)] bg-[var(--primary-soft)]"
                          : "border-[var(--border)] bg-[var(--surface-muted)] hover:border-[var(--border-strong)]"
                      }`}
                    >
                      <div className="flex items-center justify-between gap-3">
                        <div>
                          <p className="text-sm font-semibold text-[var(--foreground)]">{profile.label}</p>
                          <p className="mt-1 text-xs text-[var(--muted)]">
                            {getRoleLabel(profile.role)} · {profile.classLabel}
                          </p>
                        </div>
                        <span className="rounded-full border border-[var(--border)] bg-[var(--surface)] px-2.5 py-1 text-[11px] font-semibold text-[var(--body)]">
                          {getDomainLabel(profile.domain)}
                        </span>
                      </div>
                    </Link>
                  );
                })}
              </div>
            )}
          </div>

          <nav className="scrollbar-thin flex-1 overflow-y-auto px-3 py-4">
            <p className="px-2 pb-3 text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">Navigation</p>
            {loading && !activeProfile ? (
              <div className="space-y-2 px-1 animate-pulse">
                <div className="h-10 rounded-2xl bg-[var(--surface-muted)]" />
                <div className="h-10 rounded-2xl bg-[var(--surface-muted)]" />
                <div className="h-10 rounded-2xl bg-[var(--surface-muted)]" />
              </div>
            ) : (
              <div className="space-y-1">
                {visibleNavigationItems.map((item) => {
                  const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
                  return (
                    <Link
                      key={item.href}
                      href={withProfile(item.href, activeProfile?.profileId ?? "student-minji")}
                      className={`flex items-center justify-between rounded-2xl px-3 py-2.5 text-sm font-medium transition ${
                        active
                          ? "bg-[var(--primary-soft)] text-[var(--primary)]"
                          : "text-[var(--body)] hover:bg-[var(--surface-muted)]"
                      }`}
                    >
                      <span>{item.label}</span>
                      {active ? <span className="h-2.5 w-2.5 rounded-full bg-[var(--primary)]" /> : null}
                    </Link>
                  );
                })}
              </div>
            )}
          </nav>

          <div className="border-t border-[var(--border)] bg-[var(--surface-muted)] px-5 py-4">
            <div className="space-y-2">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">Current scope</p>
              {loading && !activeProfile ? (
                <div className="animate-pulse space-y-2">
                  <div className="h-4 w-24 rounded-full bg-[var(--surface)]" />
                  <div className="h-4 w-36 rounded-full bg-[var(--surface)]" />
                </div>
              ) : activeProfile ? (
                <>
                  <p className="text-sm font-semibold text-[var(--foreground)]">{self?.courseLabel ?? activeProfile.courseLabel}</p>
                  <p className="text-sm leading-6 text-[var(--muted)]">
                    {getDomainLabel(self?.domain ?? activeProfile.domain)} · {self?.actorId ?? activeProfile.actorId}
                  </p>
                </>
              ) : (
                <p className="text-sm leading-6 text-[var(--muted)]">현재 스코프를 불러오지 못했습니다.</p>
              )}
            </div>
          </div>
        </aside>

        <div className="flex min-h-screen flex-col gap-4">
          <div className="panel-card flex flex-col gap-4 px-4 py-4 lg:hidden">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">Knowloop</p>
                <h2 className="mt-2 text-lg font-semibold text-[var(--foreground)]">{activeProfile?.label ?? "워크스페이스 로딩 중"}</h2>
                <p className="mt-1 text-sm text-[var(--muted)]">
                  {activeProfile
                    ? `${getRoleLabel(activeProfile.role)} · ${self?.courseLabel ?? activeProfile.courseLabel} · ${self?.classLabel ?? activeProfile.classLabel}`
                    : "현재 역할과 수업 맥락을 불러오는 중입니다."}
                </p>
              </div>
              <span className="rounded-full bg-[var(--primary-soft)] px-3 py-1.5 text-xs font-semibold text-[var(--primary)]">
                {activeProfile ? getDomainLabel(self?.domain ?? activeProfile.domain) : "Loading"}
              </span>
            </div>

            <div className="space-y-2">
              <label htmlFor="mobile-profile-switcher" className="muted-label">
                역할과 맥락 전환
              </label>
              <select
                id="mobile-profile-switcher"
                className="w-full rounded-2xl border border-[var(--border)] bg-[var(--surface-muted)] px-3 py-3 text-sm font-medium text-[var(--body)] outline-none"
                value={activeProfile?.profileId ?? ""}
                onChange={(event) => handleProfileChange(event.target.value)}
                disabled={!profiles.length}
              >
                {profiles.map((profile) => (
                  <option key={profile.profileId} value={profile.profileId}>
                    {profile.label} · {getRoleLabel(profile.role)}
                  </option>
                ))}
              </select>
            </div>

            {error ? (
              <div className="rounded-[20px] border border-dashed border-[var(--danger)] bg-[var(--danger-soft)]/50 px-4 py-4 text-sm leading-6 text-[var(--body)]">
                <p className="font-semibold text-[var(--foreground)]">entry setup failed</p>
                <p className="mt-2">{error}</p>
                <button
                  type="button"
                  onClick={() => void refresh()}
                  className="mt-4 rounded-2xl border border-[var(--border)] bg-[var(--surface)] px-4 py-2.5 text-sm font-semibold text-[var(--body)]"
                >
                  다시 불러오기
                </button>
              </div>
            ) : null}

            <nav className="scrollbar-thin -mx-1 flex gap-2 overflow-x-auto px-1 pb-1">
              {visibleNavigationItems.map((item) => {
                const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
                return (
                  <Link
                    key={item.href}
                    href={withProfile(item.href, activeProfile?.profileId ?? "student-minji")}
                    className={`shrink-0 rounded-full px-3 py-2 text-sm font-medium transition ${
                      active
                        ? "bg-[var(--primary)] text-white"
                        : "border border-[var(--border)] bg-[var(--surface-muted)] text-[var(--body)]"
                    }`}
                  >
                    {item.label}
                  </Link>
                );
              })}
            </nav>
          </div>

          <div className="flex min-h-[calc(100vh-2rem)] flex-col">{children}</div>
        </div>
      </div>
    </div>
  );
}
