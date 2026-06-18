"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { useAppSession } from "@/components/auth-provider";
import { getActivePlan } from "@/lib/api";

export default function PlanAliasPage() {
  const router = useRouter();
  const { session, isReady } = useAppSession();

  useEffect(() => {
    if (!isReady) return;
    let active = true;
    const token = session?.access_token;
    if (!token) {
      router.replace("/plans");
      return;
    }
    void getActivePlan(token)
      .then((plan) => {
        if (active) router.replace(`/plans/${plan.plan_id}`);
      })
      .catch(() => {
        if (active) router.replace("/plans");
      });
    return () => {
      active = false;
    };
  }, [isReady, router, session?.access_token]);

  return (
    <section className="panel loading-card">
      <p className="kicker">Plan</p>
      <h1>Opening active plan</h1>
      <p className="muted">If there is no active plan, you will go to the plan workspace.</p>
    </section>
  );
}
