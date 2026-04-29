"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import {
  fetchContextSelf,
  fetchWorkspaceContexts,
  type BootstrapContext,
  type BootstrapContextSelf,
} from "@/lib/context-bootstrap";

type ContextBootstrapState = {
  contexts: BootstrapContext[];
  activeContext: BootstrapContext | null;
  self: BootstrapContextSelf | null;
  loading: boolean;
  error: string | null;
  requestedContextId: string | null;
  refresh: () => Promise<void>;
};

const ContextBootstrapContext = createContext<ContextBootstrapState | null>(null);

export function ContextBootstrapProvider({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const requestedContextId = searchParams.get("context");
  const queryString = searchParams.toString();

  const [contexts, setContexts] = useState<BootstrapContext[]>([]);
  const [self, setSelf] = useState<BootstrapContextSelf | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const requestSequenceRef = useRef(0);

  const refresh = useCallback(async () => {
    const requestSequence = requestSequenceRef.current + 1;
    requestSequenceRef.current = requestSequence;

    setLoading(true);
    setError(null);
    setSelf(null);

    try {
      const nextContexts = await fetchWorkspaceContexts();

      if (requestSequence !== requestSequenceRef.current) {
        return;
      }

      if (!nextContexts.length) {
        setContexts([]);
        setSelf(null);
        setError("No workspace contexts are available for this frontend.");
        setLoading(false);
        return;
      }

      const resolvedContext =
        nextContexts.find((context) => context.contextId === requestedContextId) ??
        nextContexts[0];

      setContexts(nextContexts);

      if (resolvedContext.contextId !== requestedContextId) {
        const nextParams = new URLSearchParams(queryString);
        nextParams.set("context", resolvedContext.contextId);
        nextParams.delete("profile");
        router.replace(`${pathname}?${nextParams.toString()}`, { scroll: false });
      }

      const nextSelf = await fetchContextSelf(resolvedContext.contextId);

      if (requestSequence !== requestSequenceRef.current) {
        return;
      }

      setSelf(nextSelf);
    } catch (caughtError) {
      const message =
        caughtError instanceof Error
          ? caughtError.message
          : "Failed to load the context bootstrap state.";
      setError(message);
      setContexts([]);
      setSelf(null);
    } finally {
      if (requestSequence === requestSequenceRef.current) {
        setLoading(false);
      }
    }
  }, [pathname, queryString, requestedContextId, router]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const activeContext = useMemo(() => {
    if (loading && requestedContextId) {
      return contexts.find((context) => context.contextId === requestedContextId) ?? null;
    }

    if (self?.contextId) {
      return contexts.find((context) => context.contextId === self.contextId) ?? null;
    }

    if (requestedContextId) {
      return contexts.find((context) => context.contextId === requestedContextId) ?? null;
    }

    return contexts[0] ?? null;
  }, [contexts, loading, requestedContextId, self?.contextId]);

  const value = useMemo<ContextBootstrapState>(
    () => ({
      contexts,
      activeContext,
      self,
      loading,
      error,
      requestedContextId,
      refresh,
    }),
    [contexts, activeContext, self, loading, error, requestedContextId, refresh],
  );

  return <ContextBootstrapContext.Provider value={value}>{children}</ContextBootstrapContext.Provider>;
}

export function useContextBootstrap() {
  const value = useContext(ContextBootstrapContext);

  if (!value) {
    throw new Error("useContextBootstrap must be used within ContextBootstrapProvider.");
  }

  return value;
}
