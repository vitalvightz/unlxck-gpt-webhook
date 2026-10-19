"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { useAppSession } from "@/components/auth-provider";
import { useOnReconnect } from "@/components/connection-status-banner";
import { getActivePlan } from "@/lib/api";
import { isNetworkFailure } from "@/lib/connectivity";

export default function PlanAliasPage() {
  const router = useRouter();
  const { session, isReady } = useAppSession();
  const [connectionLost, setConnectionLost] = useState(false);
  const [attempt, setAttempt] = useState(0);
  useOnReconnect(() => {
    setConnectionLost(false);
    setAttempt((value) => value + 1);
  }, connectionLost);

  useEffect(() => {
    let active = true;
    if (!isReady) {
      return () => {
        active = false;
      };
    }
    const token = session?.access_token;
    if (!token) {
      router.replace("/plans");
      return () => {
        active = false;
      };
    }
    void getActivePlan(token)
      .then((plan) => {
        if (active) router.replace(`/plans/${plan.plan_id}`);
      })
      .catch((error) => {
        if (!active) return;
        // Offline is not "no active plan": stay put and resume on reconnect
        // instead of dropping the athlete on an empty-looking plan list.
        if (isNetworkFailure(error)) {
          setConnectionLost(true);
          return;
        }
        router.replace("/plans");
      });
    return () => {
      active = false;
    };
  }, [attempt, isReady, router, session?.access_token]);

  return (
    <section className="panel loading-card" aria-busy={!connectionLost}>
      <p className="kicker">{connectionLost ? "Connection offline" : "Unlxcking…"}</p>
      <h1>{connectionLost ? "Your plan is waiting." : "Opening active plan"}</h1>
      <p className="muted">
        {connectionLost
          ? "We’ll open it the moment you’re back online."
          : "If there is no active plan, you will go to the plan workspace."}
      </p>
      {connectionLost ? (
        <div className="hero-actions">
          <button type="button" className="cta" onClick={() => setAttempt((value) => value + 1)}>
            Retry
          </button>
        </div>
      ) : null}
    </section>
  );
}
