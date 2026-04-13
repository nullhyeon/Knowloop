"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import type { ReactNode } from "react";

import {
  demoProfiles,
  getDomainLabel,
  getNavigationForRole,
  getProfileById,
  getRoleLabel,
  withProfile,
} from "@/lib/demo-data";

type ConsoleShellProps = {
  children: ReactNode;
};

export function ConsoleShell({ children }: ConsoleShellProps) {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const activeProfile = getProfileById(searchParams.get("profile"));
  const visibleNavigationItems = getNavigationForRole(activeProfile.role);

  function resolveProfileHref(profileId: string) {
    const profile = getProfileById(profileId);
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
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">
              Knowloop
            </p>
            <div className="mt-3 space-y-1">
              <h2 className="text-lg font-semibold text-[var(--foreground)]">{activeProfile.label}</h2>
              <p className="text-sm leading-6 text-[var(--muted)]">
                {getRoleLabel(activeProfile.role)} 워크스페이스 · {activeProfile.classLabel}
              </p>
            </div>
            <p className="mt-3 text-sm leading-6 text-[var(--body)]">{activeProfile.description}</p>
          </div>

          <div className="border-b border-[var(--border)] px-5 py-4">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">
              역할 전환
            </p>
            <div className="mt-3 space-y-2">
              {demoProfiles.map((profile) => {
                const active = profile.profileId === activeProfile.profileId;
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
          </div>

          <nav className="scrollbar-thin flex-1 overflow-y-auto px-3 py-4">
            <p className="px-2 pb-3 text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">
              Navigation
            </p>
            <div className="space-y-1">
              {visibleNavigationItems.map((item) => {
                const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
                return (
                  <Link
                    key={item.href}
                    href={withProfile(item.href, activeProfile.profileId)}
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
          </nav>

          <div className="border-t border-[var(--border)] bg-[var(--surface-muted)] px-5 py-4">
            <div className="space-y-2">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">
                Current scope
              </p>
              <p className="text-sm font-semibold text-[var(--foreground)]">{activeProfile.courseLabel}</p>
              <p className="text-sm leading-6 text-[var(--muted)]">
                {getDomainLabel(activeProfile.domain)} · {activeProfile.actorId}
              </p>
            </div>
          </div>
        </aside>

        <div className="flex min-h-screen flex-col gap-4">
          <div className="panel-card flex flex-col gap-4 px-4 py-4 lg:hidden">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">
                  Knowloop
                </p>
                <h2 className="mt-2 text-lg font-semibold text-[var(--foreground)]">{activeProfile.label}</h2>
                <p className="mt-1 text-sm text-[var(--muted)]">
                  {getRoleLabel(activeProfile.role)} · {activeProfile.courseLabel} · {activeProfile.classLabel}
                </p>
              </div>
              <span className="rounded-full bg-[var(--primary-soft)] px-3 py-1.5 text-xs font-semibold text-[var(--primary)]">
                {getDomainLabel(activeProfile.domain)}
              </span>
            </div>

            <div className="space-y-2">
              <label htmlFor="mobile-profile-switcher" className="muted-label">
                역할과 맥락 전환
              </label>
              <select
                id="mobile-profile-switcher"
                className="w-full rounded-2xl border border-[var(--border)] bg-[var(--surface-muted)] px-3 py-3 text-sm font-medium text-[var(--body)] outline-none"
                value={activeProfile.profileId}
                onChange={(event) => handleProfileChange(event.target.value)}
              >
                {demoProfiles.map((profile) => (
                  <option key={profile.profileId} value={profile.profileId}>
                    {profile.label} · {getRoleLabel(profile.role)}
                  </option>
                ))}
              </select>
            </div>

            <nav className="scrollbar-thin -mx-1 flex gap-2 overflow-x-auto px-1 pb-1">
              {visibleNavigationItems.map((item) => {
                const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
                return (
                  <Link
                    key={item.href}
                    href={withProfile(item.href, activeProfile.profileId)}
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
