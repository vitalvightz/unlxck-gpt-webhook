"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { useAppSession } from "@/components/auth-provider";

function LoadingCard({ label }: { label: string }) {
  return (
    <section className="panel loading-card">
      <p className="kicker">Unlxcking…</p>
      <h1>{label}</h1>
      <p className="muted">We are checking your session and restoring the correct athlete workspace.</p>
    </section>
  );
}

export function RequireAuth({
  children,
  adminOnly = false,
}: Readonly<{ children: React.ReactNode; adminOnly?: boolean }>) {
  const router = useRouter();
  const { isReady, isMeHydrated, hasTransientMeError, session, me } = useAppSession();
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

  // Connection loss is surfaced by the app-wide ConnectionStatusBanner in the
  // root layout, which also re-hydrates the profile on reconnect.

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

  return <>{body}</>;
}
