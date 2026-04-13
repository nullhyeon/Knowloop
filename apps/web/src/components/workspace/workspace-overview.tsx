"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";

import {
  demoProfiles,
  getDomainLabel,
  getProfileById,
  getRecentContextsForProfile,
  getRoleLabel,
  withProfile,
} from "@/lib/demo-data";

import { ScopeHeader } from "@/components/console/scope-header";

export function WorkspaceOverview() {
  const searchParams = useSearchParams();
  const activeProfile = getProfileById(searchParams.get("profile"));
  const recentContexts = getRecentContextsForProfile(activeProfile.profileId);

  return (
    <div className="flex flex-1 flex-col gap-5 pb-6">
      <ScopeHeader
        title="Workspace"
        description="현재 어떤 역할과 수업 맥락으로 들어갈지 정하는 진입 화면입니다. 기술적인 헤더 값을 직접 입력하지 않고, 역할 카드와 최근 맥락을 통해 바로 작업을 시작할 수 있어야 합니다."
        role={getRoleLabel(activeProfile.role)}
        course={activeProfile.courseLabel}
        classNameLabel={activeProfile.classLabel}
        domain={getDomainLabel(activeProfile.domain)}
      />

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.15fr)_360px]">
        <section className="panel-card px-6 py-6 lg:px-7">
          <div className="max-w-3xl space-y-2">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">
              Role-aware entry
            </p>
            <h2 className="text-2xl font-semibold tracking-[-0.02em] text-[var(--foreground)]">
              지금 어떤 관점으로 Knowloop에 들어갈지 먼저 선택합니다.
            </h2>
            <p className="text-sm leading-7 text-[var(--body)]">
              학생은 질문과 학습 기록을, 강사는 반복 질문과 공식 지식 반영을, 검토자와 운영자는 유지보수와 정합성 점검을 중심으로 같은 시스템을 보게 됩니다.
            </p>
          </div>

          <div className="mt-6 grid gap-4 md:grid-cols-2">
            {demoProfiles.map((profile) => {
              const active = profile.profileId === activeProfile.profileId;
              return (
                <article
                  key={profile.profileId}
                  className={`rounded-[24px] border px-5 py-5 transition ${
                    active
                      ? "border-[var(--primary)] bg-[var(--primary-soft)]"
                      : "border-[var(--border)] bg-[var(--surface-muted)]"
                  }`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-lg font-semibold text-[var(--foreground)]">{profile.label}</p>
                      <p className="mt-1 text-sm text-[var(--muted)]">
                        {getRoleLabel(profile.role)} · {profile.courseLabel} · {profile.classLabel}
                      </p>
                    </div>
                    <span className="rounded-full border border-[var(--border)] bg-[var(--surface)] px-2.5 py-1 text-[11px] font-semibold text-[var(--body)]">
                      {getDomainLabel(profile.domain)}
                    </span>
                  </div>
                  <p className="mt-4 text-sm leading-6 text-[var(--body)]">{profile.description}</p>
                  <div className="mt-5 flex flex-wrap gap-2">
                    <Link
                      href={withProfile(profile.landingSurface, profile.profileId)}
                      className="rounded-2xl bg-[var(--primary)] px-4 py-2.5 text-sm font-semibold text-white transition hover:opacity-90"
                    >
                      이 역할로 시작하기
                    </Link>
                    <Link
                      href={withProfile("/workspace", profile.profileId)}
                      className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] px-4 py-2.5 text-sm font-semibold text-[var(--body)]"
                    >
                      맥락만 전환하기
                    </Link>
                  </div>
                </article>
              );
            })}
          </div>
        </section>

        <div className="flex flex-col gap-5">
          <section className="panel-card px-5 py-5">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">
              Continue where you left off
            </p>
            <h3 className="mt-2 text-lg font-semibold text-[var(--foreground)]">최근 맥락 이어서 보기</h3>
            <div className="mt-4 space-y-3">
              {recentContexts.map((context) => (
                <Link
                  key={context.contextId}
                  href={withProfile(context.href, context.profileId)}
                  className="block rounded-[20px] border border-[var(--border)] bg-[var(--surface-muted)] px-4 py-4 transition hover:border-[var(--border-strong)]"
                >
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-sm font-semibold text-[var(--foreground)]">{context.title}</p>
                    <span className="rounded-full bg-[var(--surface)] px-2.5 py-1 text-[11px] font-semibold text-[var(--muted)]">
                      {context.badge}
                    </span>
                  </div>
                  <p className="mt-2 text-sm leading-6 text-[var(--body)]">{context.summary}</p>
                </Link>
              ))}
            </div>
          </section>

          <section className="panel-card px-5 py-5">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">
              Recommended surfaces
            </p>
            <h3 className="mt-2 text-lg font-semibold text-[var(--foreground)]">이 역할에서 바로 쓰는 화면</h3>
            <div className="mt-4 space-y-3 text-sm leading-6 text-[var(--body)]">
              <div className="rounded-[20px] border border-[var(--border)] bg-[var(--surface-muted)] px-4 py-4">
                <p className="font-semibold text-[var(--foreground)]">Ask</p>
                <p className="mt-1">질문과 grounded answer, write-back 흐름을 한 화면에서 확인합니다.</p>
              </div>
              <div className="rounded-[20px] border border-[var(--border)] bg-[var(--surface-muted)] px-4 py-4">
                <p className="font-semibold text-[var(--foreground)]">Wiki</p>
                <p className="mt-1">공식 위키의 문서, 근거, 최근 수정 흔적을 살펴봅니다.</p>
              </div>
              <div className="rounded-[20px] border border-[var(--border)] bg-[var(--surface-muted)] px-4 py-4">
                <p className="font-semibold text-[var(--foreground)]">Learning</p>
                <p className="mt-1">학생 역할에서는 최근 혼동 개념과 복습 액션을 바로 이어 볼 수 있습니다.</p>
              </div>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
