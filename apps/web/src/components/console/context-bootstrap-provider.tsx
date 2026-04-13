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
  fetchContextProfiles,
  fetchContextSelf,
  type BootstrapContextSelf,
  type BootstrapProfile,
} from "@/lib/context-bootstrap";

type ContextBootstrapState = {
  profiles: BootstrapProfile[];
  activeProfile: BootstrapProfile | null;
  self: BootstrapContextSelf | null;
  loading: boolean;
  error: string | null;
  requestedProfileId: string | null;
  refresh: () => Promise<void>;
};

const ContextBootstrapContext = createContext<ContextBootstrapState | null>(null);

export function ContextBootstrapProvider({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const requestedProfileId = searchParams.get("profile");
  const queryString = searchParams.toString();

  const [profiles, setProfiles] = useState<BootstrapProfile[]>([]);
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
      const nextProfiles = await fetchContextProfiles();

      if (requestSequence !== requestSequenceRef.current) {
        return;
      }

      if (!nextProfiles.length) {
        setProfiles([]);
        setSelf(null);
        setError("No context profiles are available for this frontend.");
        setLoading(false);
        return;
      }

      const resolvedProfile = nextProfiles.find((profile) => profile.profileId === requestedProfileId) ?? nextProfiles[0];

      setProfiles(nextProfiles);

      if (resolvedProfile.profileId !== requestedProfileId) {
        const nextParams = new URLSearchParams(queryString);
        nextParams.set("profile", resolvedProfile.profileId);
        router.replace(`${pathname}?${nextParams.toString()}`, { scroll: false });
      }

      const nextSelf = await fetchContextSelf(resolvedProfile.profileId);

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
      setProfiles([]);
      setSelf(null);
    } finally {
      if (requestSequence === requestSequenceRef.current) {
        setLoading(false);
      }
    }
  }, [pathname, queryString, requestedProfileId, router]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const activeProfile = useMemo(() => {
    if (loading && requestedProfileId) {
      return profiles.find((profile) => profile.profileId === requestedProfileId) ?? null;
    }

    if (self?.profileId) {
      return profiles.find((profile) => profile.profileId === self.profileId) ?? null;
    }

    if (requestedProfileId) {
      return profiles.find((profile) => profile.profileId === requestedProfileId) ?? null;
    }

    return profiles[0] ?? null;
  }, [loading, profiles, requestedProfileId, self?.profileId]);

  const value = useMemo<ContextBootstrapState>(
    () => ({
      profiles,
      activeProfile,
      self,
      loading,
      error,
      requestedProfileId,
      refresh,
    }),
    [profiles, activeProfile, self, loading, error, requestedProfileId, refresh],
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
