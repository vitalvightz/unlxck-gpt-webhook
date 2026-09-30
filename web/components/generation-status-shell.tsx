"use client";

import { useAppSession } from "./auth-provider";
import { GenerationStatusProvider, useGenerationStatus } from "./generation-status-provider";
import { GlobalGenerationStatus, getGenerationStatusTarget } from "./global-generation-status";
import { MobileTabBar } from "./mobile-tab-bar";
import { useEffect, useRef, type ReactNode } from "react";
import { useRouter } from "next/navigation";

function ApprovedGenerationHandoff() {
  const { me } = useAppSession();
  const router = useRouter();
  const { phase, jobId, planId, terminalStatus, source, athleteId } = useGenerationStatus();
  const followedJob = useRef<string | null>(null);

  useEffect(() => {
    if (me?.profile.role !== "athlete" || source !== "admin_triage_resume" || !jobId) return;
    if (phase === "queued" || phase === "running" || phase === "finalizing") {
      followedJob.current = jobId;
      return;
    }
    const target = getGenerationStatusTarget(phase, planId, terminalStatus, source, athleteId);
    if (phase === "completed" && target && followedJob.current === jobId) {
      followedJob.current = null;
      router.replace(target);
    }
  }, [athleteId, jobId, me?.profile.role, phase, planId, router, source, terminalStatus]);

  return null;
}

interface GenerationStatusShellProps {
  children: ReactNode;
}

export function GenerationStatusShell({ children }: GenerationStatusShellProps) {
  const { session } = useAppSession();
  const token = session?.access_token ?? null;

  return (
    <GenerationStatusProvider token={token}>
      <ApprovedGenerationHandoff />
      {children}
      <GlobalGenerationStatus />
      <MobileTabBar />
    </GenerationStatusProvider>
  );
}
