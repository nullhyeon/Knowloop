export type KnowloopRole = "student" | "instructor" | "operator" | "validator";
export type KnowloopDomain = "academic" | "operations" | "review";

export type NavigationItem = {
  label: string;
  href: string;
  roles: KnowloopRole[];
  implemented: boolean;
};

export type WorkspaceContext = {
  contextId: string;
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

export type WorkspaceEntrySuggestion = {
  suggestionId: string;
  contextId: string;
  title: string;
  summary: string;
  href: string;
  badge: string;
};

export const navigationItems: NavigationItem[] = [
  { label: "Workspace", href: "/workspace", roles: ["student", "instructor", "operator", "validator"], implemented: true },
  { label: "Ask", href: "/ask", roles: ["student", "instructor"], implemented: true },
  { label: "Learning", href: "/learning", roles: ["student"], implemented: true },
  { label: "Wiki", href: "/wiki", roles: ["student", "instructor", "validator"], implemented: true },
  { label: "Review", href: "/review", roles: ["instructor", "operator", "validator"], implemented: true },
  { label: "Insights", href: "/insights", roles: ["instructor"], implemented: true },
  { label: "Sources", href: "/sources", roles: ["instructor", "operator", "validator"], implemented: true },
  { label: "Maintenance", href: "/maintenance", roles: ["instructor", "validator"], implemented: true },
];

export const workspaceContexts: WorkspaceContext[] = [
  {
    contextId: "student-calculus-a",
    label: "학생 컨텍스트",
    role: "student",
    actorId: "stu-kim-minji",
    courseId: "course-calculus-1",
    courseLabel: "미적분 I",
    classId: "class-calculus-1-2026-spring-a",
    classLabel: "A반",
    domain: "academic",
    landingSurface: "/ask",
    description: "학생이 근거 기반 질문을 남기고 개인 학습 흐름을 이어가는 컨텍스트입니다.",
  },
  {
    contextId: "instructor-calculus-a",
    label: "강사 컨텍스트",
    role: "instructor",
    actorId: "ins-calculus-team",
    courseId: "course-calculus-1",
    courseLabel: "미적분 I",
    classId: "class-calculus-1-2026-spring-a",
    classLabel: "A반",
    domain: "academic",
    landingSurface: "/insights",
    description: "반복 질문, 후보 지식, 공식 위키 반영 상태를 관리하는 강사 컨텍스트입니다.",
  },
  {
    contextId: "operator-academic-office",
    label: "운영 컨텍스트",
    role: "operator",
    actorId: "ops-academic-office",
    courseId: "course-calculus-1",
    courseLabel: "미적분 I",
    classId: "class-calculus-1-2026-spring-a",
    classLabel: "A반",
    domain: "operations",
    landingSurface: "/sources",
    description: "공지, 정책, 운영 source를 관리하는 운영 컨텍스트입니다.",
  },
  {
    contextId: "validator-course-admin",
    label: "검토 컨텍스트",
    role: "validator",
    actorId: "val-course-admin",
    courseId: "course-calculus-1",
    courseLabel: "미적분 I",
    classId: "class-calculus-1-2026-spring-a",
    classLabel: "A반",
    domain: "review",
    landingSurface: "/review",
    description: "후보 지식 승격, 동기화 복구, 유지보수 상태를 검토하는 컨텍스트입니다.",
  },
];

export const defaultContextId = "student-calculus-a";

const entrySuggestions: WorkspaceEntrySuggestion[] = [
  {
    suggestionId: "entry-student-ask",
    contextId: "student-calculus-a",
    title: "Ask에서 학습 질문 이어가기",
    summary: "학생 관점에서 근거, 세션 저장, 학습 노트 반영을 한 흐름으로 확인합니다.",
    href: "/ask",
    badge: "학생 흐름",
  },
  {
    suggestionId: "entry-instructor-insights",
    contextId: "instructor-calculus-a",
    title: "Insights에서 반복 질문 확인",
    summary: "강사 관점에서 수업 패턴과 review 후보를 연결해 봅니다.",
    href: "/insights",
    badge: "강사 흐름",
  },
  {
    suggestionId: "entry-validator-review",
    contextId: "validator-course-admin",
    title: "Review에서 승격 상태 확인",
    summary: "검토 관점에서 candidate, patch preview, wiki sync 상태를 점검합니다.",
    href: "/review",
    badge: "검토 흐름",
  },
];

export function getWorkspaceContextById(contextId?: string | null): WorkspaceContext {
  return (
    workspaceContexts.find((context) => context.contextId === contextId) ??
    workspaceContexts.find((context) => context.contextId === defaultContextId) ??
    workspaceContexts[0]
  );
}

export function getRoleLabel(role: KnowloopRole): string {
  switch (role) {
    case "student":
      return "학생";
    case "instructor":
      return "강사";
    case "operator":
      return "운영";
    case "validator":
      return "검토";
    default:
      return role;
  }
}

export function getDomainLabel(domain: KnowloopDomain): string {
  switch (domain) {
    case "academic":
      return "Academic";
    case "operations":
      return "Operations";
    case "review":
      return "Review";
    default:
      return domain;
  }
}

export function getNavigationForRole(role: KnowloopRole): NavigationItem[] {
  return navigationItems.filter((item) => item.implemented && item.roles.includes(role));
}

export function withContext(href: string, contextId: string): string {
  const [pathname, queryString = ""] = href.split("?");
  const params = new URLSearchParams(queryString);
  params.delete("profile");
  params.set("context", contextId);
  const resolvedQuery = params.toString();
  return resolvedQuery ? `${pathname}?${resolvedQuery}` : pathname;
}

export function getEntrySuggestionsForContext(contextId?: string | null): WorkspaceEntrySuggestion[] {
  const context = getWorkspaceContextById(contextId);
  const directSuggestions = entrySuggestions.filter(
    (suggestion) => suggestion.contextId === context.contextId,
  );
  return directSuggestions.length ? directSuggestions : entrySuggestions.slice(0, 2);
}

export function buildKnowloopContextHeaders(context: WorkspaceContext | string): Record<string, string> {
  const resolvedContext =
    typeof context === "string" ? getWorkspaceContextById(context) : context;
  return {
    "X-Knowloop-Role": resolvedContext.role,
    "X-Knowloop-Actor-Id": resolvedContext.actorId,
    "X-Knowloop-Course-Id": resolvedContext.courseId,
    "X-Knowloop-Class-Id": resolvedContext.classId,
    "X-Knowloop-Domain": resolvedContext.domain,
  };
}
