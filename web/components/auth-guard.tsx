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

function ConnectionLostBanner({
  isRetrying,
  onRetry,
}: {
  isRetrying: boolean;
  onRetry: () => void;
}) {
  return (
    <div className="connection-lost-banner" role="status" aria-live="polite">
      <span className="connection-lost-dot" aria-hidden="true" />
      <span className="connection-lost-text">
        {isRetrying ? "Reconnecting…" : "No internet connection"}
      </span>
      <button
        type="button"
        className="connection-lost-retry"
        onClick={onRetry}
        disabled={isRetrying}
      >
        {isRetrying ? "Retrying…" : "Retry"}
      </button>
    </div>
  );
}

export function RequireAuth({
  children,
  adminOnly = false,
}: Readonly<{ children: React.ReactNode; adminOnly?: boolean }>) {
  const router = useRouter();
  const { isReady, isMeHydrated, hasTransientMeError, session, me, refreshMe } = useAppSession();
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

  // The connection banner is a small, persistent overlay shown on every guarded
  // page (admin and athlete alike) whenever profile access could not be reached.
  // It reads as a plain "no internet" indicator rather than an app-specific
  // failure, and the provider keeps auto-retrying in the background.
  const connectionBanner =
    isReady && session && hasTransientMeError ? (
      <ConnectionLostBanner
        isRetrying={isRetryingRecovery}
        onRetry={() => void handleRetryRecovery()}
      />
    ) : null;

  let body: React.ReactNode;
  if (!isReady) {
    body = <LoadingCard label="Checking your access" />;
  } else if (!session) {
    body = <LoadingCard label="Redirecting to login" />;
  } else if (adminOnly && hasTransientMeError && !me) {
    body = <LoadingCard label="Restoring admin access" />;
  } else if (adminOnly && !isMeHydrated) {
    body = <LoadingCard label="Restoring admin access" />;
  } else if (isMeHydrated && !me) {
    body = <LoadingCard label="Redirecting to login" />;
  } else if (adminOnly && role !== "admin") {
    body = <LoadingCard label="Redirecting to your athlete view" />;
  } else {
    body = children;
  }

  return (
    <>
      {connectionBanner}
      {body}
    </>
  );
}
