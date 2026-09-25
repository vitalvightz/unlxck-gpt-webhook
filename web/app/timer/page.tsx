"use client";

import { useRoundTimer } from "@/components/session-timer/round-timer-provider";

// Open to everyone, plan or not: a round timer is only a clock, and it logs nothing.
export default function TimerPage() {
  const roundTimer = useRoundTimer();

  return (
    <section className="panel today-shell today-empty-state">
      <div className="today-hero-copy">
        <p className="kicker">Tools</p>
        <h1>Round timer</h1>
        <p className="muted">
          Rounds and rest with the bell. Pick a format and go. It keeps time while you move around the app.
        </p>
      </div>
      <div className="today-action-row">
        <button type="button" className="cta" onClick={roundTimer.open}>
          {roundTimer.shown ? "Open round timer" : "Start round timer"}
        </button>
      </div>
    </section>
  );
}
