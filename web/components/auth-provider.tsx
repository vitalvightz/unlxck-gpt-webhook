"use client";

import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";

import { ApiError, getMe } from "@/lib/api";
import { getSupabaseBrowserClient } from "@/lib/supabase";
import type { MeResponse } from "@/lib/types";

type AppSession = {
  access_token: string;
};

type DemoRole = "athlete" | "admin";

type AppSessionValue = {
  isReady: boolean;
  isMeHydrated: boolean;
  session: AppSession | null;
  me: MeResponse | null;
  demoMode: boolean;
  refreshMe: () => Promise<void>;
  replaceMe: (nextMe: MeResponse | null) => void;
  signOut: () => Promise<void>;
  signInDemo: (role?: DemoRole) => Promise<void>;
};

const DEMO_MODE = process.env.NEXT_PUBLIC_DEMO_MODE === "1";
const DEMO_TOKEN_KEY = "unlxck-demo-token";
const AppSessionContext = createContext<AppSessionValue | undefined>(undefined);

function tokenForRole(role: DemoRole): string {
  return role === "admin" ? "demo-admin" : "demo-athlete";
}

export function AuthProvider({ children }: Readonly<{ children: ReactNode }>) {
  const [isReady, setIsReady] = useState(false);
  const [isMeHydrated, setIsMeHydrated] = useState(false);
  const [session, setSession] = useState<AppSession | null>(null);
  const [me, setMe] = useState<MeResponse | null>(null);
  const handledAccessTokenRef = useRef<string | null>(null);
  const loadGenerationRef = useRef(0);

  async function loadMe(nextSession: AppSession | null, options: { allowRefresh?: boolean } = {}) {
    const allowRefresh = options.allowRefresh ?? true;
    const currentLoadId = loadGenerationRef.current + 1;
    loadGenerationRef.current = currentLoadId;

    if (!nextSession?.access_token) {
      if (loadGenerationRef.current === currentLoadId) {
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

      if (!DEMO_MODE && err instanceof ApiError && err.status === 401 && allowRefresh) {
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

    if (DEMO_MODE) {
      const token = window.localStorage.getItem(DEMO_TOKEN_KEY);
      if (!token) {
        setIsReady(true);
        setIsMeHydrated(true);
        return () => {
          active = false;
        };
      }
      const nextSession = { access_token: token };
      handledAccessTokenRef.current = token;
      setSession(nextSession);
      void loadMe(nextSession);
      return () => {
        active = false;
      };
    }

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

    client.auth.getSession().then(({ data }) => {
      if (!active) {
        return;
      }
      const nextSession = data.session ? { access_token: data.session.access_token } : null;
      handledAccessTokenRef.current = nextSession?.access_token ?? null;
      setSession(nextSession);
      void loadMe(nextSession);
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

  async function refreshMe() {
    await loadMe(session);
  }

  function replaceMe(nextMe: MeResponse | null) {
    setMe(nextMe);
    setIsMeHydrated(true);
  }

  async function signInDemo(role: DemoRole = "athlete") {
    const nextSession = { access_token: tokenForRole(role) };
    window.localStorage.setItem(DEMO_TOKEN_KEY, nextSession.access_token);
    handledAccessTokenRef.current = nextSession.access_token;
    setSession(nextSession);
    setIsReady(false);
    setIsMeHydrated(false);
    await loadMe(nextSession);
  }

  async function signOut() {
    if (DEMO_MODE) {
      window.localStorage.removeItem(DEMO_TOKEN_KEY);
      handledAccessTokenRef.current = null;
      setSession(null);
      setMe(null);
      setIsReady(true);
      setIsMeHydrated(true);
      return;
    }

    try {
      await getSupabaseBrowserClient().auth.signOut();
    } catch {
      // Ignore missing client during sign-out cleanup.
    }
    handledAccessTokenRef.current = null;
    setSession(null);
    setMe(null);
    setIsReady(true);
    setIsMeHydrated(true);
  }

  return (
    <AppSessionContext.Provider
      value={{
        isReady,
        isMeHydrated,
        session,
        me,
        demoMode: DEMO_MODE,
        refreshMe,
        replaceMe,
        signOut,
        signInDemo,
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
