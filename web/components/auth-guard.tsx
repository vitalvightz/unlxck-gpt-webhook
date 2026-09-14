"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { useAppSession } from "@/components/auth-provider";
import { useTranslations as useAppTranslations } from "next-intl";


function LoadingCard({ label }: { label: string }) {
    const appText = useAppTranslations("AppText");
  return (
    <section className="panel loading-card">
      <p className="kicker">{appText("text_dc380888c4e2")}</p>
      <h1>{label}</h1>
      <p className="muted">{appText("text_de45d47694da")}</p>
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
    const appText = useAppTranslations("AppText");
  return (
    <div className="connection-lost-banner" role="status" aria-live="polite">
      <span className="connection-lost-dot" aria-hidden="true" />
      <span className="connection-lost-text">
        {isRetrying ? appText("text_27b80374e115") : appText("text_c4184bd7daac")}
      </span>
      <button
        type="button"
        className="connection-lost-retry"
        onClick={onRetry}
        disabled={isRetrying}
      >
        {isRetrying ? appText("text_a16c8b1c9595") : appText("text_942087cc2d41")}
      </button>
    </div>
  );
}

export function RequireAuth({
  children,
  adminOnly = false,
}: Readonly<{ children: React.ReactNode; adminOnly?: boolean }>) {
    const appText = useAppTranslations("AppText");
  const router = useRouter();
  const { isReady, isMeHydrated, hasTransientMeError, isAccessPending, session, me, refreshMe, signOut } = useAppSession();
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
    if (isMeHydrated && !me && !isAccessPending) {
      router.replace("/login");
      return;
    }
    if (adminOnly && role && role !== "admin") {
      router.replace("/plans");
    }
  }, [adminOnly, hasTransientMeError, isAccessPending, isMeHydrated, isReady, me, role, router, session]);

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
    body = <LoadingCard label={appText("text_d788caa307df")} />;
  } else if (!session) {
    body = <LoadingCard label={appText("text_b8e9fb2876fb")} />;
  } else if (isAccessPending) {
    body = (
      <section className="panel loading-card">
        <p className="kicker">{appText("text_9c1014e1daa5")}</p>
        <h1>{appText("text_13bda74671f3")}</h1>
        <p className="muted">{appText("text_ae7d5d58beeb")}</p>
        <button type="button" className="ghost-button" onClick={() => void signOut()}>
          {appText("text_48f0d3d397d4")}</button>
      </section>
    );
  } else if (adminOnly && hasTransientMeError && !me) {
    body = <LoadingCard label={appText("text_03a90f0be8d9")} />;
  } else if (adminOnly && !isMeHydrated) {
    body = <LoadingCard label={appText("text_03a90f0be8d9")} />;
  } else if (isMeHydrated && !me) {
    body = <LoadingCard label={appText("text_b8e9fb2876fb")} />;
  } else if (adminOnly && role !== "admin") {
    body = <LoadingCard label={appText("text_1765426315d7")} />;
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
