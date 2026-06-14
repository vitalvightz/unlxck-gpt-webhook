"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { useAppSession } from "@/components/auth-provider";

function LoadingCard({ label }: { label: string }) {
  return (
    <section className="panel loading-card">
      <p className="kicker">Loading</p>
      <h1>{label}</h1>
      <p className="muted">We are checking your session and restoring the correct athlete workspace.</p>
    </section>
  );
}

function RecoveryCard({
  adminOnly,
  isRetrying,
  onRetry,
  onSignOut,
}: {
  adminOnly: boolean;
  isRetrying: boolean;
  onRetry: () => void;
  onSignOut: () => void;
}) {
  return (
    <section className="panel loading-card auth-recovery-card" role="alert">
      <p className="kicker">{adminOnly ? "Admin access" : "Workspace"}</p>
      <h1>{adminOnly ? "Admin access needs a refresh" : "Workspace needs a refresh"}</h1>
      <p className="muted">
        Your session is still present, but profile access did not finish loading.
      </p>
      <div className="hero-actions auth-recovery-actions">
        <button type="button" className="cta" onClick={onRetry} disabled={isRetrying}>
          {isRetrying ? "Retrying..." : "Retry now"}
        </button>
        <button type="button" className="secondary-button" onClick={onSignOut} disabled={isRetrying}>
          Sign out
        </button>
      </div>
      <p className="auth-recovery-note">If the connection recovers, retry returns you to this page.</p>
    </section>
  );
}

export function RequireAuth({
  children,
  adminOnly = false,
}: Readonly<{ children: React.ReactNode; adminOnly?: boolean }>) {
  const router = useRouter();
  const { isReady, isMeHydrated, hasTransientMeError, session, me, refreshMe, signOut } = useAppSession();
  const [isRetryingRecovery, setIsRetryingRecovery] = useState(false);
  const role = me?.profile.role;

  useEffect(() => {
    if (!isReady) {
      return;
    }
    if (!session) {
      router.replace("/login");
      return;
    }
    if (adminOnly && !isMeHydrated) {
      return;
    }
    if (isMeHydrated && !me) {
      router.replace("/login");
      return;
    }
    if (adminOnly && role && role !== "admin") {
      router.replace("/plans");
    }
  }, [adminOnly, hasTransientMeError, isMeHydrated, isReady, me, role, router, session]);

  useEffect(() => {
    if (!hasTransientMeError) {
      setIsRetryingRecovery(false);
    }
  }, [hasTransientMeError]);

  async function handleRetryRecovery() {
    if (isRetryingRecovery) {
      return;
    }
    setIsRetryingRecovery(true);
    try {
      await refreshMe();
    } finally {
      setIsRetryingRecovery(false);
    }
  }

  async function handleRecoverySignOut() {
    await signOut();
    router.push("/login");
  }

  if (!isReady) {
    return <LoadingCard label="Checking your access" />;
  }
  if (!session) {
    return <LoadingCard label="Redirecting to login" />;
  }
  if (adminOnly && hasTransientMeError && session && !me) {
    return (
      <RecoveryCard
        adminOnly={adminOnly}
        isRetrying={isRetryingRecovery}
        onRetry={() => void handleRetryRecovery()}
        onSignOut={() => void handleRecoverySignOut()}
      />
    );
  }
  if (adminOnly && !isMeHydrated) {
    return <LoadingCard label={adminOnly ? "Restoring admin access" : "Restoring your workspace"} />;
  }
  if (isMeHydrated && !me) {
    return <LoadingCard label="Redirecting to login" />;
  }
  if (adminOnly && role !== "admin") {
    return <LoadingCard label="Redirecting to your athlete view" />;
  }

  return <>{children}</>;
}
