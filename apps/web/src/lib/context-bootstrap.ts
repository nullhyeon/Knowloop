import { getProfileById, type KnowloopDomain, type KnowloopRole } from "@/lib/demo-data";

export type ContextProfileApi = {
  profile_id: string;
  label: string;
  role: KnowloopRole;
  actor_id: string;
  course_id: string;
  class_id: string;
  domain: KnowloopDomain;
  landing_surface: string;
  description: string | null;
};

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

export type BootstrapProfile = {
  profileId: string;
  label: string;
  role: KnowloopRole;
  actorId: string;
  courseId: string;
  courseLabel: string;
  classId: string;
  classLabel: string;
  domain: KnowloopDomain;
  landingSurface: string;
  description: string;
};

export type BootstrapContextSelf = {
  profileId: string | null;
  profileLabel: string | null;
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

const landingSurfaceMap: Record<string, string> = {
  student_hub: "/ask",
  instructor_dashboard: "/insights",
  operations_console: "/sources",
  review_inbox: "/review",
};

function resolveLandingSurfacePath(landingSurface: string, role: KnowloopRole): string {
  if (landingSurface.startsWith("/")) {
    return landingSurface;
  }

  if (landingSurfaceMap[landingSurface]) {
    return landingSurfaceMap[landingSurface];
  }

  switch (role) {
    case "student":
      return "/ask";
    case "instructor":
      return "/insights";
    case "operator":
      return "/sources";
    case "validator":
      return "/review";
    default:
      return "/workspace";
  }
}

function fallbackCourseLabel(courseId: string): string {
  if (courseId === "course-calculus-1") {
    return "Calculus I";
  }

  return courseId;
}

function fallbackClassLabel(classId: string): string {
  if (classId === "class-calculus-1-2026-spring-a") {
    return "Class A";
  }

  return classId;
}

export function hydrateBootstrapProfile(profile: ContextProfileApi): BootstrapProfile {
  const localProfile = getProfileById(profile.profile_id);

  return {
    profileId: profile.profile_id,
    label: profile.label,
    role: profile.role,
    actorId: profile.actor_id,
    courseId: profile.course_id,
    courseLabel: localProfile.courseId === profile.course_id ? localProfile.courseLabel : fallbackCourseLabel(profile.course_id),
    classId: profile.class_id,
    classLabel: localProfile.classId === profile.class_id ? localProfile.classLabel : fallbackClassLabel(profile.class_id),
    domain: profile.domain,
    landingSurface: resolveLandingSurfacePath(profile.landing_surface, profile.role),
    description: profile.description ?? "Start Knowloop with this role and class context.",
  };
}

export function hydrateBootstrapSelf(self: ContextSelfApi): BootstrapContextSelf {
  const localProfile = getProfileById(self.profile_id);

  return {
    profileId: self.profile_id,
    profileLabel: self.profile_label,
    role: self.role,
    actorId: self.actor_id,
    courseId: self.course_id,
    courseLabel: localProfile.courseId === self.course_id ? localProfile.courseLabel : fallbackCourseLabel(self.course_id),
    classId: self.class_id,
    classLabel: localProfile.classId === self.class_id ? localProfile.classLabel : fallbackClassLabel(self.class_id),
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

export async function fetchContextProfiles(): Promise<BootstrapProfile[]> {
  const profiles = await fetchEnvelope<ContextProfileApi[]>("/api/v1/context/profiles");
  return profiles.map(hydrateBootstrapProfile);
}

export async function fetchContextSelf(profileId: string): Promise<BootstrapContextSelf> {
  const self = await fetchEnvelope<ContextSelfApi>("/api/v1/context/self", {
    headers: {
      "X-Knowloop-Profile-Id": profileId,
    },
  });

  return hydrateBootstrapSelf(self);
}
