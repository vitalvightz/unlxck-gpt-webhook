"use client";

import Link from "next/link";
import { useEffect, useRef } from "react";

import { useRoundTimer, useSavedTodayRun } from "@/components/session-timer/round-timer-provider";

// Open to everyone, plan or not: a round timer is only a clock, and it logs nothing.
export default function TimerPage() {
  const roundTimer = useRoundTimer();
  // One timer at a time: a session or sparring run already going is resumed on Today.
  const todayRunSaved = useSavedTodayRun() && !roundTimer.shown;

  // Open straight into the timer on its last setup: no screen to tap through
  // first. Once only, so closing it leaves the athlete here, not in a loop.
  const { show } = roundTimer;
  const opened = useRef(false);
  useEffect(() => {
    if (opened.current) return;
    opened.current = true;
    show();
  }, [show]);

  // Only seen behind the timer: once it is minimised, closed or blocked.
  return (
    <section className="panel today-shell today-empty-state">
      <div className="today-hero-copy">
        <h1>Round timer</h1>
        {todayRunSaved ? (
          <p className="muted">
            Your session timer is still running. Finish or close it on Today before starting the round timer.
          </p>
        ) : null}
      </div>
      <div className="today-action-row">
        {todayRunSaved ? (
          <Link href="/today#today-session" className="cta">
            Resume on Today
          </Link>
        ) : (
          <button type="button" className="cta" onClick={roundTimer.open}>
            {roundTimer.shown ? "Open round timer" : "Start round timer"}
          </button>
        )}
      </div>
    </section>
  );
}
