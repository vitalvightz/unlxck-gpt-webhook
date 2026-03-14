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
  const { isReady, session, me } = useAppSession();

  useEffect(() => {
    if (!isReady) {
      return;
    }
    if (!session) {
      router.replace("/login");
      return;
    }
    if (adminOnly && me?.profile.role !== "admin") {
      router.replace("/plans");
    }
  }, [adminOnly, isReady, me?.profile.role, router, session]);

  if (!isReady) {
    return <LoadingCard label="Checking your access" />;
  }
  if (!session) {
    return <LoadingCard label="Redirecting to login" />;
  }
  if (adminOnly && me?.profile.role !== "admin") {
    return <LoadingCard label="Redirecting to your athlete view" />;
  }

  return <>{children}</>;
}
