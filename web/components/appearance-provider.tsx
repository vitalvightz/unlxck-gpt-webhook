"use client";

import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

export type SurfaceMode = "dark" | "light";

type AppearanceContextValue = {
  surfaceMode: SurfaceMode;
  setSurfaceMode: (mode: SurfaceMode) => void;
};

const STORAGE_KEY = "unlxck-surface-mode";
const AppearanceContext = createContext<AppearanceContextValue | undefined>(undefined);

export function AppearanceProvider({ children }: Readonly<{ children: ReactNode }>) {
  const [surfaceMode, setSurfaceMode] = useState<SurfaceMode>("dark");
  const [hasLoadedPreference, setHasLoadedPreference] = useState(false);

  useEffect(() => {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    const nextMode = stored === "light" ? "light" : "dark";
    document.documentElement.dataset.surfaceMode = nextMode;
    setSurfaceMode(nextMode);
    setHasLoadedPreference(true);
  }, []);

  useEffect(() => {
    if (!hasLoadedPreference) {
      return;
    }
    document.documentElement.dataset.surfaceMode = surfaceMode;
    window.localStorage.setItem(STORAGE_KEY, surfaceMode);
  }, [hasLoadedPreference, surfaceMode]);

  const value = useMemo(
    () => ({
      surfaceMode,
      setSurfaceMode,
    }),
    [surfaceMode],
  );

  return <AppearanceContext.Provider value={value}>{children}</AppearanceContext.Provider>;
}

export function useAppearance() {
  const context = useContext(AppearanceContext);
  if (!context) {
    throw new Error("useAppearance must be used within AppearanceProvider.");
  }
  return context;
}
