"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useAppSession } from "./auth-provider";
import { updateMe } from "@/lib/api";
import { getAuthenticatedLandingHref, needsStartingPath } from "@/lib/auth-routing";
import { requiresComplianceAcceptance } from "@/lib/compliance";
import styles from "./starting-path-screen.module.css";

export function StartingPathScreen() {
  const { session, me, isMeHydrated, hasTransientMeError, replaceMe, refreshMe, signOut } = useAppSession();
  const router = useRouter();
  const [saving, setSaving] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSigningOut, setSigningOut] = useState(false);
  const locked = useRef(false);
  const ready = isMeHydrated && me && !hasTransientMeError;
  const mustAccept = requiresComplianceAcceptance(me);

  useEffect(() => {
    if (ready && (mustAccept || !needsStartingPath(me))) {
      router.replace(getAuthenticatedLandingHref(me));
    }
  }, [ready, mustAccept, me, router]);

  async function choose(path: "tracking_first" | "plan_first") {
    if (locked.current || isSigningOut || !session || !ready || mustAccept) return;
    locked.current = true;
    setSaving(path); setError(null);
    try {
      const result = await updateMe(session.access_token, { starting_path: path });
      if (result.profile.starting_path !== path) throw new Error("Your choice could not be saved. Try again.");
      replaceMe(result);
      router.replace(path === "tracking_first" ? "/today" : "/quick-build");
    } catch {
      setError("Your choice could not be saved. Try again.");
      locked.current = false; setSaving(null);
    }
  }

  if (!ready) return <section className="panel" aria-busy={!hasTransientMeError}>
    <h1>{hasTransientMeError ? "Couldn’t load your account" : "Loading your account…"}</h1>
    {hasTransientMeError ? <button className="secondary-button" onClick={() => void refreshMe()}>Retry</button> : null}
  </section>;
  if (mustAccept || !needsStartingPath(me)) return <p role="status">Opening your workspace…</p>;

  return <section className={styles.root} aria-labelledby="starting-heading">
    <header className={styles.brand}><span>UNLXCK</span><button className={styles.accountAction} type="button" disabled={Boolean(saving) || isSigningOut} onClick={async () => {
      setSigningOut(true);
      await signOut();
      router.replace("/login");
    }}>{isSigningOut ? "Signing out…" : "Sign out"}</button></header>
    <div className={styles.intro}>
      <h1 id="starting-heading">How would you like to start?</h1>
      <p>Choose your starting point. You can use both whenever you want.</p>
    </div>
    <div className={styles.choices} aria-busy={Boolean(saving)}>
      <button className={styles.choice} type="button" disabled={Boolean(saving) || isSigningOut} onClick={() => void choose("plan_first")}>
        <span className={styles.icon} aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M3 9v6M6 6v12M9 9v6M9 12h6M15 9v6M18 6v12M21 9v6" /></svg></span>
        <span className={styles.copy}><strong>Build my training plan</strong><span>Personalised S&amp;C around your sport, schedule and goals.</span></span>
        <span className={styles.action}>{saving === "plan_first" ? "Saving…" : "Build a plan"}<span aria-hidden="true"> →</span></span>
      </button>
      <button className={styles.choice} type="button" disabled={Boolean(saving) || isSigningOut} onClick={() => void choose("tracking_first")}>
        <span className={styles.icon} aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M9 5H6v15h12V5h-3M9 3h6v4H9zM9 12l2 2 4-4M9 17h6" /></svg></span>
        <span className={styles.copy}><strong>I already have a coach or plan</strong><span>Track your training without building a programme.</span></span>
        <span className={styles.action}>{saving === "tracking_first" ? "Saving…" : "Start tracking"}<span aria-hidden="true"> →</span></span>
      </button>
    </div>
    {error ? <p role="alert" className={styles.error}>{error}</p> : null}
    <p className={styles.footer}>Two starting points. One UNLXCK account.</p>
  </section>;
}
