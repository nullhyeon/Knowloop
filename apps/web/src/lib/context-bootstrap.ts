import {
  buildKnowloopContextHeaders,
  getWorkspaceContextById,
  workspaceContexts,
  type KnowloopDomain,
  type KnowloopRole,
  type WorkspaceContext,
} from "@/lib/workspace-context";

export type BootstrapContext = WorkspaceContext;

export type ContextSelfApi = {
  profile_id: string | null;
  profile_label: string | null;
  role: KnowloopRole;
  actor_id: string;
  course_id: string;
  class_id: string;
  domain: KnowloopDomain | null;
  domain_was_explicit: boolean;
};

export type BootstrapContextSelf = {
  contextId: string | null;
  contextLabel: string | null;
  role: KnowloopRole;
  actorId: string;
  courseId: string;
  courseLabel: string;
  classId: string;
  classLabel: string;
  domain: KnowloopDomain | null;
  domainWasExplicit: boolean;
};

type ApiEnvelope<T> = {
  status: string;
  data: T;
  meta?: Record<string, unknown>;
};

function fallbackCourseLabel(courseId: string): string {
  if (courseId === "course-calculus-1") {
    return "미적분 I";
  }

  return courseId;
}

function fallbackClassLabel(classId: string): string {
  if (classId === "class-calculus-1-2026-spring-a") {
    return "A반";
  }

  return classId;
}

export function hydrateBootstrapSelf(
  self: ContextSelfApi,
  context: BootstrapContext,
): BootstrapContextSelf {
  return {
    contextId: context.contextId,
    contextLabel: context.label,
    role: self.role,
    actorId: self.actor_id,
    courseId: self.course_id,
    courseLabel:
      context.courseId === self.course_id
        ? context.courseLabel
        : fallbackCourseLabel(self.course_id),
    classId: self.class_id,
    classLabel:
      context.classId === self.class_id ? context.classLabel : fallbackClassLabel(self.class_id),
    domain: self.domain,
    domainWasExplicit: self.domain_was_explicit,
  };
}

async function fetchEnvelope<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    cache: "no-store",
    headers: {
      Accept: "application/json",
      ...(init?.headers ?? {}),
    },
  });

  if (!response.ok) {
    throw new Error(`Context bootstrap request failed with ${response.status}.`);
  }

  const payload = (await response.json()) as ApiEnvelope<T>;
  return payload.data;
}

export async function fetchWorkspaceContexts(): Promise<BootstrapContext[]> {
  return workspaceContexts;
}

export async function fetchContextSelf(contextId: string): Promise<BootstrapContextSelf> {
  const context = getWorkspaceContextById(contextId);
  const self = await fetchEnvelope<ContextSelfApi>("/api/v1/context/self", {
    headers: buildKnowloopContextHeaders(context),
  });

  return hydrateBootstrapSelf(self, context);
}
