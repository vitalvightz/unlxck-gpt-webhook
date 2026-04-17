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
  const { isReady, isMeHydrated, session, me, demoMode, signInDemo } = useAppSession();
  const role = me?.profile.role;

  useEffect(() => {
    if (!isReady) {
      return;
    }
    if (!session) {
      if (adminOnly && demoMode) {
        void signInDemo("admin");
        return;
      }
      router.replace("/login");
      return;
    }
    if (!isMeHydrated) {
      return;
    }
    if (!me) {
      router.replace("/login");
      return;
    }
    if (adminOnly && role && role !== "admin") {
      router.replace("/plans");
    }
  }, [adminOnly, demoMode, isMeHydrated, isReady, me, role, router, session, signInDemo]);

  if (!isReady) {
    return <LoadingCard label="Checking your access" />;
  }
  if (!session) {
    return <LoadingCard label={adminOnly && demoMode ? "Restoring demo admin access" : "Redirecting to login"} />;
  }
  if (!isMeHydrated) {
    return <LoadingCard label={adminOnly ? "Restoring admin access" : "Restoring your workspace"} />;
  }
  if (!me) {
    return <LoadingCard label="Redirecting to login" />;
  }
  if (adminOnly && role !== "admin") {
    return <LoadingCard label="Redirecting to your athlete view" />;
  }

  return <>{children}</>;
}
