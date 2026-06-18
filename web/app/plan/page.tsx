"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { useAppSession } from "@/components/auth-provider";
import { getActivePlan } from "@/lib/api";

// `/plan` is an alias that resolves intelligently (Block 4 / PR #1800):
//   - active plan exists -> /plans/[active_plan_id]
//   - no active plan      -> /plans (the plan manager)
export default function PlanAliasPage() {
  const router = useRouter();
  const { isReady, session } = useAppSession();

  useEffect(() => {
    if (!isReady) {
      return;
    }
    const token = session?.access_token;
    if (!token) {
      router.replace("/plans");
      return;
    }
    let active = true;
    getActivePlan(token)
      .then((response) => {
        if (!active) {
          return;
        }
        const planId = response.active_plan?.plan_id;
        router.replace(planId ? `/plans/${planId}` : "/plans");
      })
      .catch(() => {
        if (active) {
          router.replace("/plans");
        }
      });
    return () => {
      active = false;
    };
  }, [isReady, router, session?.access_token]);

  return (
    <section className="panel loading-card">
      <p className="kicker">Plan</p>
      <h1>Opening your active plan…</h1>
      <p className="muted">Resolving the plan that controls Today.</p>
    </section>
  );
}
