"use client";

import { createContext, useContext, useEffect, useRef, useState, type Dispatch, type ReactNode, type SetStateAction } from "react";

import { ApiError, getMe } from "@/lib/api";
import { getSupabaseBrowserClient } from "@/lib/supabase";
import type { AppearanceMode, MeResponse } from "@/lib/types";

type AppSession = {
  access_token: string;
};


type AppSessionValue = {
  isReady: boolean;
  isMeHydrated: boolean;
  session: AppSession | null;
  me: MeResponse | null;
  previewAppearanceMode: Dispatch<SetStateAction<AppearanceMode | null>>;
  refreshMe: () => Promise<void>;
  replaceMe: (nextMe: MeResponse | null) => void;
  signOut: () => Promise<void>;
};

const AppSessionContext = createContext<AppSessionValue | undefined>(undefined);

function applyAppearanceMode(mode: AppearanceMode) {
  if (typeof document === "undefined") {
    return;
  }
  document.documentElement.dataset.theme = mode;
  document.documentElement.style.colorScheme = mode;
}

export function AuthProvider({ children }: Readonly<{ children: ReactNode }>) {
  const [isReady, setIsReady] = useState(false);
  const [isMeHydrated, setIsMeHydrated] = useState(false);
  const [session, setSession] = useState<AppSession | null>(null);
  const [me, setMe] = useState<MeResponse | null>(null);
  const [appearancePreview, setAppearancePreview] = useState<AppearanceMode | null>(null);
  const handledAccessTokenRef = useRef<string | null>(null);
  const loadGenerationRef = useRef(0);

  async function loadMe(nextSession: AppSession | null, options: { allowRefresh?: boolean } = {}) {
    const allowRefresh = options.allowRefresh ?? true;
    const currentLoadId = loadGenerationRef.current + 1;
    loadGenerationRef.current = currentLoadId;

    if (!nextSession?.access_token) {
      if (loadGenerationRef.current === currentLoadId) {
        setAppearancePreview(null);
        setMe(null);
        setIsMeHydrated(true);
        setIsReady(true);
      }
      return;
    }

    setIsMeHydrated(false);

    try {
      const nextMe = await getMe(nextSession.access_token);
      if (loadGenerationRef.current !== currentLoadId) {
        return;
      }
      setMe(nextMe);
      setSession(nextSession);
    } catch (err) {
      if (loadGenerationRef.current !== currentLoadId) {
        return;
      }

      if (err instanceof ApiError && err.status === 401 && allowRefresh) {
        try {
          const client = getSupabaseBrowserClient();
          const refreshResult = await client.auth.refreshSession();
          const refreshedAccessToken = refreshResult.data.session?.access_token ?? null;
          if (refreshedAccessToken) {
            const refreshedSession = { access_token: refreshedAccessToken };
            handledAccessTokenRef.current = refreshedAccessToken;
            await loadMe(refreshedSession, { allowRefresh: false });
            return;
          }
        } catch {
          // Treat refresh failures as a genuine session expiry below.
        }
      }

      if (err instanceof ApiError && err.status === 401) {
        setAppearancePreview(null);
        setSession(null);
        setMe(null);
      }
    } finally {
      if (loadGenerationRef.current === currentLoadId) {
        setIsMeHydrated(true);
        setIsReady(true);
      }
    }
  }

  useEffect(() => {
    let active = true;
    let subscription: { unsubscribe: () => void } | null = null;

    let client;
    try {
      client = getSupabaseBrowserClient();
    } catch {
      setIsReady(true);
      setIsMeHydrated(true);
      return () => {
        active = false;
      };
    }

    client.auth
      .getSession()
      .then(({ data }) => {
        if (!active) {
          return;
        }
        const nextSession = data.session ? { access_token: data.session.access_token } : null;
        handledAccessTokenRef.current = nextSession?.access_token ?? null;
        setSession(nextSession);
        void loadMe(nextSession);
      })
      .catch(async () => {
        if (!active) {
          return;
        }
        try {
          await client.auth.signOut();
        } catch {
          // Ignore cleanup failures after a stale browser auth session.
        }
        handledAccessTokenRef.current = null;
        setAppearancePreview(null);
        setSession(null);
        setMe(null);
        setIsMeHydrated(true);
        setIsReady(true);
      });

    const authState = client.auth.onAuthStateChange((_event, nextSession) => {
      if (!active) {
        return;
      }
      const mappedSession = nextSession ? { access_token: nextSession.access_token } : null;
      const nextToken = mappedSession?.access_token ?? null;
      if (handledAccessTokenRef.current === nextToken) {
        return;
      }
      handledAccessTokenRef.current = nextToken;
      setSession(mappedSession);
      void loadMe(mappedSession);
    });
    subscription = authState.data.subscription;

    return () => {
      active = false;
      subscription?.unsubscribe();
    };
  }, []);

  useEffect(() => {
    if (!isReady) {
      return;
    }
    applyAppearanceMode(
      appearancePreview ?? (session && me?.profile.appearance_mode === "light" ? "light" : "dark"),
    );
  }, [appearancePreview, isReady, session, me?.profile.appearance_mode]);

  async function refreshMe() {
    await loadMe(session);
  }

  function replaceMe(nextMe: MeResponse | null) {
    setMe(nextMe);
    setIsMeHydrated(true);
  }

  async function signOut() {
    try {
      await getSupabaseBrowserClient().auth.signOut();
    } catch {
      // Ignore missing client during sign-out cleanup.
    }
    handledAccessTokenRef.current = null;
    setAppearancePreview(null);
    setSession(null);
    setMe(null);
    setIsReady(true);
    setIsMeHydrated(true);
    applyAppearanceMode("dark");
  }

  return (
    <AppSessionContext.Provider
      value={{
        isReady,
        isMeHydrated,
        session,
        me,
        previewAppearanceMode: setAppearancePreview,
        refreshMe,
        replaceMe,
        signOut,
      }}
    >
      {children}
    </AppSessionContext.Provider>
  );
}

export function useAppSession() {
  const context = useContext(AppSessionContext);
  if (!context) {
    throw new Error("useAppSession must be used within AuthProvider.");
  }
  return context;
}
