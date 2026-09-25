"use client";

import Link from "next/link";

import { useRoundTimer, useSavedTodayRun } from "@/components/session-timer/round-timer-provider";

// Open to everyone, plan or not: a round timer is only a clock, and it logs nothing.
export default function TimerPage() {
  const roundTimer = useRoundTimer();
  // One timer at a time: a session or sparring run already going is resumed on Today.
  const todayRunSaved = useSavedTodayRun() && !roundTimer.shown;

  return (
    <section className="panel today-shell today-empty-state">
      <div className="today-hero-copy">
        <p className="kicker">Tools</p>
        <h1>Round timer</h1>
        <p className="muted">
          {todayRunSaved
            ? "Your session timer is still running. Finish or close it on Today before starting the round timer."
            : "Rounds and rest with the bell. Pick a format and go. It keeps time while you move around the app."}
        </p>
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
