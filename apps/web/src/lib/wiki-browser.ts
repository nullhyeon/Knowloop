"use client";

import type { BootstrapContextSelf, BootstrapProfile } from "@/lib/context-bootstrap";

type ApiEnvelope<T> = {
  status: string;
  data: T;
  meta?: Record<string, unknown>;
};

export type WikiPageListItemApi = {
  page_id: string;
  domain: string;
  title: string;
  summary: string;
  updated_at: string;
};

export type WikiPageDetailApi = {
  page_id: string;
  domain: string;
  title: string;
  summary: string;
  course_id: string;
  class_scope: string;
  updated_at: string;
  source_refs: string[];
  candidate_refs: string[];
  body_markdown: string;
};

export type WikiBrowserListItem = {
  pageId: string;
  domain: string;
  title: string;
  summary: string;
  section: string;
  scopeLabel: string;
  updatedAt: string;
};

export type WikiBodyBlock =
  | {
      kind: "heading";
      level: 1 | 2 | 3;
      content: string;
    }
  | {
      kind: "paragraph";
      content: string;
    }
  | {
      kind: "list";
      items: string[];
    };

export type WikiBrowserDetail = WikiBrowserListItem & {
  sourceRefs: string[];
  candidateRefs: string[];
  bodyBlocks: WikiBodyBlock[];
  stateLabel: string;
};

type WikiFetchContext = {
  profileId: string;
};

function buildRequestHeaders(context: WikiFetchContext): HeadersInit {
  return {
    Accept: "application/json",
    "X-Knowloop-Profile-Id": context.profileId,
  };
}

function formatTimestamp(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat("ko-KR", {
    month: "long",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(parsed);
}

function formatDomainTag(domain: string): string {
  switch (domain) {
    case "faq":
      return "FAQ";
    case "concepts":
      return "개념";
    case "misconceptions":
      return "오개념";
    case "courses":
      return "코스 문서";
    case "operations":
      return "운영";
    default:
      break;
  }

  if (domain.toUpperCase() === domain) {
    return domain;
  }

  return domain
    .split(/[-_]+/g)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function inferStateLabel(detail: WikiPageDetailApi): string {
  if (detail.candidate_refs.length > 0) {
    return "Candidate linked";
  }
  if (detail.source_refs.length > 0) {
    return "Source traced";
  }
  return "Metadata light";
}

function parseMarkdownBlocks(bodyMarkdown: string): WikiBodyBlock[] {
  const lines = bodyMarkdown.split(/\r?\n/);
  const blocks: WikiBodyBlock[] = [];
  let paragraphBuffer: string[] = [];
  let listBuffer: string[] = [];

  function flushParagraph() {
    if (!paragraphBuffer.length) {
      return;
    }

    blocks.push({
      kind: "paragraph",
      content: paragraphBuffer.join(" ").trim(),
    });
    paragraphBuffer = [];
  }

  function flushList() {
    if (!listBuffer.length) {
      return;
    }

    blocks.push({
      kind: "list",
      items: [...listBuffer],
    });
    listBuffer = [];
  }

  for (const rawLine of lines) {
    const line = rawLine.trim();

    if (!line) {
      flushParagraph();
      flushList();
      continue;
    }

    const headingMatch = line.match(/^(#{1,3})\s+(.*)$/);
    if (headingMatch) {
      flushParagraph();
      flushList();
      blocks.push({
        kind: "heading",
        level: headingMatch[1].length as 1 | 2 | 3,
        content: headingMatch[2].trim(),
      });
      continue;
    }

    const listMatch = line.match(/^[-*]\s+(.*)$/);
    if (listMatch) {
      flushParagraph();
      listBuffer.push(listMatch[1].trim());
      continue;
    }

    flushList();
    paragraphBuffer.push(line);
  }

  flushParagraph();
  flushList();

  return blocks;
}

function resolveScopeLabel(
  domain: string,
  self: BootstrapContextSelf | null,
  activeProfile: BootstrapProfile | null,
  courseId?: string,
  classScope?: string,
): string {
  const resolvedCourseId = courseId ?? self?.courseId ?? activeProfile?.courseId ?? "";
  const resolvedClassScope = classScope ?? self?.classId ?? activeProfile?.classId ?? "";
  const courseLabel =
    resolvedCourseId && self?.courseId === resolvedCourseId
      ? self.courseLabel
      : activeProfile?.courseId === resolvedCourseId
        ? activeProfile.courseLabel
        : resolvedCourseId;
  const classLabel =
    resolvedClassScope && self?.classId === resolvedClassScope
      ? self.classLabel
      : activeProfile?.classId === resolvedClassScope
        ? activeProfile.classLabel
        : resolvedClassScope;

  return [courseLabel, classLabel, formatDomainTag(domain)].filter(Boolean).join(" · ");
}

function mapListItem(
  page: WikiPageListItemApi,
  options: {
    self: BootstrapContextSelf | null;
    activeProfile: BootstrapProfile | null;
  },
): WikiBrowserListItem {
  const { self, activeProfile } = options;
  return {
    pageId: page.page_id,
    domain: page.domain,
    title: page.title,
    summary: page.summary,
    section: formatDomainTag(page.domain),
    scopeLabel: resolveScopeLabel(page.domain, self, activeProfile),
    updatedAt: formatTimestamp(page.updated_at),
  };
}

function mapDetail(
  detail: WikiPageDetailApi,
  options: {
    self: BootstrapContextSelf | null;
    activeProfile: BootstrapProfile | null;
  },
): WikiBrowserDetail {
  const { self, activeProfile } = options;
  return {
    pageId: detail.page_id,
    domain: detail.domain,
    title: detail.title,
    summary: detail.summary,
    section: formatDomainTag(detail.domain),
    scopeLabel: resolveScopeLabel(detail.domain, self, activeProfile, detail.course_id, detail.class_scope),
    updatedAt: formatTimestamp(detail.updated_at),
    sourceRefs: detail.source_refs,
    candidateRefs: detail.candidate_refs,
    bodyBlocks: parseMarkdownBlocks(detail.body_markdown),
    stateLabel: inferStateLabel(detail),
  };
}

async function fetchEnvelope<T>(path: string, init: RequestInit): Promise<ApiEnvelope<T>> {
  const response = await fetch(path, {
    ...init,
    cache: "no-store",
  });

  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as
      | { error?: { code?: string; message?: string } }
      | null;

    const code = payload?.error?.code;
    const message = payload?.error?.message;
    throw new Error(message ?? code ?? `Wiki request failed with ${response.status}.`);
  }

  return (await response.json()) as ApiEnvelope<T>;
}

export async function fetchWikiPageList(
  context: WikiFetchContext,
  query: string,
  self: BootstrapContextSelf | null,
  activeProfile: BootstrapProfile | null,
): Promise<WikiBrowserListItem[]> {
  const normalizedQuery = query.trim();
  const limit = 50;
  let offset = 0;
  let total = Number.POSITIVE_INFINITY;
  const pages: WikiPageListItemApi[] = [];

  while (offset < total) {
    const searchParams = new URLSearchParams({
      limit: String(limit),
      offset: String(offset),
    });
    if (normalizedQuery) {
      searchParams.set("q", normalizedQuery);
    }

    const envelope = await fetchEnvelope<WikiPageListItemApi[]>(`/api/v1/wiki/pages?${searchParams.toString()}`, {
      headers: buildRequestHeaders(context),
    });

    pages.push(...envelope.data);
    total = Number(envelope.meta?.total ?? pages.length);

    if (!envelope.data.length) {
      break;
    }

    offset += envelope.data.length;
  }

  return pages.map((page) => mapListItem(page, { self, activeProfile }));
}

export async function fetchWikiPageDetail(
  context: WikiFetchContext,
  pageId: string,
  self: BootstrapContextSelf | null,
  activeProfile: BootstrapProfile | null,
): Promise<WikiBrowserDetail> {
  const envelope = await fetchEnvelope<WikiPageDetailApi>(`/api/v1/wiki/pages/${pageId}`, {
    headers: buildRequestHeaders(context),
  });

  return mapDetail(envelope.data, { self, activeProfile });
}
