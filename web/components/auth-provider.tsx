"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

import { ApiError, getMe } from "@/lib/api";
import { getSupabaseBrowserClient } from "@/lib/supabase";
import type { AppearanceMode, MeResponse } from "@/lib/types";

type AppSession = {
  access_token: string;
};

type DemoRole = "athlete" | "admin";

type AppSessionValue = {
  isReady: boolean;
  session: AppSession | null;
  me: MeResponse | null;
  demoMode: boolean;
  refreshMe: () => Promise<void>;
  signOut: () => Promise<void>;
  signInDemo: (role?: DemoRole) => Promise<void>;
};

const DEMO_MODE = process.env.NEXT_PUBLIC_DEMO_MODE === "1";
const DEMO_TOKEN_KEY = "unlxck-demo-token";
const AppSessionContext = createContext<AppSessionValue | undefined>(undefined);

function tokenForRole(role: DemoRole): string {
  return role === "admin" ? "demo-admin" : "demo-athlete";
}

function applyAppearanceMode(mode: AppearanceMode) {
  if (typeof document === "undefined") {
    return;
  }
  document.documentElement.dataset.theme = mode;
  document.documentElement.style.colorScheme = mode;
}

export function AuthProvider({ children }: Readonly<{ children: ReactNode }>) {
  const [isReady, setIsReady] = useState(false);
  const [session, setSession] = useState<AppSession | null>(null);
  const [me, setMe] = useState<MeResponse | null>(null);

  async function loadMe(nextSession: AppSession | null) {
    if (!nextSession?.access_token) {
      setMe(null);
      setIsReady(true);
      return;
    }

    try {
      const nextMe = await getMe(nextSession.access_token);
      setMe(nextMe);
    } catch (err) {
      setMe(null);
      // If the token is rejected as unauthorized, clear the stale session so
      // the browser stops hammering /api/me with an invalid credential.
      if (err instanceof ApiError && err.status === 401) {
        if (!DEMO_MODE) {
          try {
            await getSupabaseBrowserClient().auth.signOut();
          } catch {
            // Ignore errors during cleanup sign-out.
          }
        }
        setSession(null);
      }
    } finally {
      setIsReady(true);
    }
  }

  useEffect(() => {
    let active = true;
    let subscription: { unsubscribe: () => void } | null = null;

    if (DEMO_MODE) {
      const token = window.localStorage.getItem(DEMO_TOKEN_KEY);
      if (!token) {
        setIsReady(true);
        return () => {
          active = false;
        };
      }
      const nextSession = { access_token: token };
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
      return () => {
        active = false;
      };
    }

    // Use onAuthStateChange as the single source of truth for session and /api/me
    // loads. The INITIAL_SESSION event fires on subscription with the stored
    // session, so a separate getSession() call is only used to set the session
    // state for the initial render without triggering a duplicate /api/me call.
    client.auth.getSession().then(({ data }) => {
      if (!active) {
        return;
      }
      const nextSession = data.session ? { access_token: data.session.access_token } : null;
      setSession(nextSession);
    });

    const authState = client.auth.onAuthStateChange((_event, nextSession) => {
      if (!active) {
        return;
      }
      const mappedSession = nextSession ? { access_token: nextSession.access_token } : null;
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
    applyAppearanceMode(session && me?.profile.appearance_mode === "light" ? "light" : "dark");
  }, [isReady, session, me?.profile.appearance_mode]);

  async function refreshMe() {
    await loadMe(session);
  }

  async function signInDemo(role: DemoRole = "athlete") {
    const nextSession = { access_token: tokenForRole(role) };
    window.localStorage.setItem(DEMO_TOKEN_KEY, nextSession.access_token);
    setSession(nextSession);
    setIsReady(false);
    await loadMe(nextSession);
  }

  async function signOut() {
    if (DEMO_MODE) {
      window.localStorage.removeItem(DEMO_TOKEN_KEY);
      setSession(null);
      setMe(null);
      setIsReady(true);
      applyAppearanceMode("dark");
      return;
    }

    try {
      await getSupabaseBrowserClient().auth.signOut();
    } catch {
      // Ignore missing client during sign-out cleanup.
    }
    setSession(null);
    setMe(null);
    setIsReady(true);
    applyAppearanceMode("dark");
  }

  return (
    <AppSessionContext.Provider value={{ isReady, session, me, demoMode: DEMO_MODE, refreshMe, signOut, signInDemo }}>
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
