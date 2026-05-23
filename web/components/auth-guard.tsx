"use client";

import { useEffect } from "react";
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

  if (!isReady) {
    return <LoadingCard label="Checking your access" />;
  }
  if (!session) {
    return <LoadingCard label="Redirecting to login" />;
  }
  if (!isMeHydrated) {
    return <LoadingCard label={adminOnly ? "Restoring admin access" : "Restoring your workspace"} />;
  }
  if (hasTransientMeError && session && !me) {
    return <LoadingCard label="Restoring your workspace" />;
  }
  if (!me) {
    return <LoadingCard label="Redirecting to login" />;
  }
  if (adminOnly && role !== "admin") {
    return <LoadingCard label="Redirecting to your athlete view" />;
  }

  return <>{children}</>;
}
