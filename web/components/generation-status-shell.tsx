"use client";

import { useAppSession } from "./auth-provider";
import { GenerationStatusProvider } from "./generation-status-provider";
import { GlobalGenerationStatus } from "./global-generation-status";
import type { ReactNode } from "react";

interface GenerationStatusShellProps {
  children: ReactNode;
}

export function GenerationStatusShell({ children }: GenerationStatusShellProps) {
  const { session } = useAppSession();
  const token = session?.access_token ?? null;

  return (
    <GenerationStatusProvider token={token}>
      {children}
      <GlobalGenerationStatus />
    </GenerationStatusProvider>
  );
}
