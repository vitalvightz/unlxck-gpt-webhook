"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { listCustomPlans } from "@/lib/api";
import type { CustomPlan } from "@/lib/api-schema.generated";
import styles from "./custom-plan-builder.module.css";
export function SavedCustomPlans({ accessToken }: { accessToken: string }) {
  const [plans, setPlans] = useState<CustomPlan[]>([]);
  const [error, setError] = useState<string>();
  const [loading, setLoading] = useState(true);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    void listCustomPlans(accessToken, controller.signal)
      .then((rows) => {
        if (!Array.isArray(rows)) throw new Error("Unable to load saved custom plans.");
        if (!controller.signal.aborted) {
          setPlans(rows);
          setError(undefined);
        }
      })
      .catch((reason) => {
        if (!controller.signal.aborted)
          setError(reason instanceof Error ? reason.message : "Unable to load saved custom plans.");
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [accessToken, retry]);
  return (
    <section id="custom-plans" aria-label="Saved custom plans" className={styles.saved}>
      <div className={styles.row}>
        <h2>Custom plans</h2>
        <Link className="ghost-button" href="/plans/custom">
          New plan
        </Link>
      </div>
      {loading ? (
        <p role="status">Loading custom plans…</p>
      ) : error ? (
        <div>
          <p role="alert">{error}</p>
          <button
            className="ghost-button"
            onClick={() => {
              setLoading(true);
              setError(undefined);
              setRetry((n) => n + 1);
            }}
          >
            Retry custom plans
          </button>
        </div>
      ) : plans.length ? (
        <ul>
          {plans.map((plan) => (
            <li key={plan.id}>
              <Link href={`/plans/custom?plan=${plan.id}`} className={styles.savedLink}>
                <strong>{plan.name}</strong>
                <span>{plan.incomplete ? "Draft" : "Ready"}</span>
                <small>
                  {plan.sessions.length} sessions ·{" "}
                  {Array.from(new Set(plan.sessions.map((s) => s.weekday ?? "Unassigned"))).join(", ") ||
                    "No days assigned"}
                </small>
              </Link>
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted">No saved custom plans yet. Build your own training week.</p>
      )}
    </section>
  );
}
