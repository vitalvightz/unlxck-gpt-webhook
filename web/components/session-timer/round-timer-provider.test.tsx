import test from "node:test";
import assert from "node:assert/strict";

import "../test-dom";
import { act } from "react";
import { createRoot } from "react-dom/client";

import TimerPage from "@/app/timer/page";
import { AuthProvider } from "@/components/auth-provider";
import { TodaySessionPanel } from "@/components/today/today-session-panel";
import { ToastProvider } from "@/components/toast-provider";
import { resolveTrainingDay, toISODate } from "@/lib/camp-map";
import type { TodayCommandView } from "@/lib/types";
import {
  CONTACT_RUN_KEY_PREFIX,
  ROUND_TIMER_STORAGE_KEY,
  RoundTimerProvider,
  SESSION_RUN_KEY_PREFIX,
  useRoundTimer,
} from "./round-timer-provider";

const TODAY = toISODate(resolveTrainingDay(new Date()));

/** Every timer on screen, full size or minimised. */
function timersOnScreen(): number {
  return document.querySelectorAll(".st-root, .st-mini").length;
}

/** Today with a coach-led contact the athlete can time, cleared to train. */
function contactDay(): TodayCommandView {
  return {
    active_plan: { id: "plan-1", name: "Camp", phase: "SPP" },
    today: {
      training_day: TODAY,
      recommendation_state: "train_as_planned",
      decision_tier: "green",
      warnings: [],
      next_session: {
        session_id: `${TODAY}-flush`,
        title: "Mobility flush",
        calendar_date: TODAY,
        session_relation: "today",
        effective_load: "low",
        coach_led_contact: "Hard sparring (coach-led)",
      },
      session_scope: "today",
      session_label: "Today's session",
      completion_status: "started",
    },
    risk_watch: [],
    open_injuries: [],
    week_summary: {},
    quick_actions: [],
  } as TodayCommandView;
}

function TryRoundTimer() {
  const roundTimer = useRoundTimer();
  return (
    <button type="button" data-testid="try-round" onClick={roundTimer.open}>
      try
    </button>
  );
}

function ShownFlag() {
  return <p data-testid="flag">{useRoundTimer().shown ? "shown" : "hidden"}</p>;
}

test("the round timer opens from the timer page, minimises to its mini bar, and closes", async () => {
  window.localStorage.clear();
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => {
    root.render(
      <RoundTimerProvider>
        <TimerPage />
        <ShownFlag />
      </RoundTimerProvider>,
    );
  });

  const flag = () => container.querySelector('[data-testid="flag"]')?.textContent;
  assert.equal(flag(), "hidden");
  assert.equal(document.querySelector(".st-root"), null);

  const start = [...container.querySelectorAll("button")].find((b) => b.textContent === "Start round timer");
  assert.ok(start);
  await act(async () => start.click());
  assert.equal(flag(), "shown");
  assert.ok(document.querySelector('.st-root[role="dialog"]'));
  assert.ok([...container.querySelectorAll("button")].some((b) => b.textContent === "Open round timer"));

  const minimise = document.querySelector<HTMLButtonElement>('[aria-label="Minimise timer"]');
  assert.ok(minimise);
  await act(async () => minimise.click());
  assert.equal(document.querySelector(".st-root"), null);
  const mini = document.querySelector<HTMLButtonElement>(".st-mini");
  assert.ok(mini);
  assert.equal(flag(), "shown");

  await act(async () => mini.click());
  assert.ok(document.querySelector(".st-root"));

  await act(async () => root.unmount());
  container.remove();
});

test("without a provider the round timer reads as closed", async () => {
  const container = document.createElement("div");
  const root = createRoot(container);
  await act(async () => root.render(<ShownFlag />));
  assert.equal(container.textContent, "hidden");
  await act(async () => root.unmount());
});

test("a saved planned run blocks the round timer: it is resumed on Today, and only one timer ever shows", async () => {
  window.localStorage.clear();
  // 1-2. A planned session timer was started on Today, then the athlete left Today.
  window.localStorage.setItem(`${SESSION_RUN_KEY_PREFIX}plan-1:${TODAY}-flush:${TODAY}`, "{}");
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => {
    root.render(
      <RoundTimerProvider>
        <TimerPage />
        <TryRoundTimer />
      </RoundTimerProvider>,
    );
  });

  // 3. The timer page points back to the running session instead of starting rounds.
  assert.ok(![...container.querySelectorAll("button")].some((b) => b.textContent === "Start round timer"));
  const resume = container.querySelector<HTMLAnchorElement>('a[href="/today#today-session"]');
  assert.equal(resume?.textContent, "Resume on Today");

  // Any other way in is refused too.
  await act(async () => container.querySelector<HTMLButtonElement>('[data-testid="try-round"]')?.click());
  assert.equal(timersOnScreen(), 0);
  assert.equal(window.localStorage.getItem(ROUND_TIMER_STORAGE_KEY), null);

  await act(async () => root.unmount());
  container.remove();
  window.localStorage.clear();
});

test("returning to Today with a saved contact run shows that one timer, never a round timer beside it", async () => {
  window.localStorage.clear();
  window.localStorage.setItem(`${CONTACT_RUN_KEY_PREFIX}plan-1:${TODAY}`, "{}");
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => {
    root.render(
      <AuthProvider>
        <ToastProvider>
          <RoundTimerProvider>
            <TryRoundTimer />
            <TodaySessionPanel state={contactDay()} structuredPlan={null} token="" onRefresh={async () => {}} />
          </RoundTimerProvider>
        </ToastProvider>
      </AuthProvider>,
    );
  });
  assert.equal(timersOnScreen(), 1);
  await act(async () => container.querySelector<HTMLButtonElement>('[data-testid="try-round"]')?.click());
  assert.equal(timersOnScreen(), 1);
  assert.equal(window.localStorage.getItem(ROUND_TIMER_STORAGE_KEY), null);

  await act(async () => root.unmount());
  container.remove();
  window.localStorage.clear();
});

test("a round timer already up keeps the screen: Today's saved run waits instead of stacking", async () => {
  window.localStorage.clear();
  window.localStorage.setItem(ROUND_TIMER_STORAGE_KEY, "{}");
  window.localStorage.setItem(`${CONTACT_RUN_KEY_PREFIX}plan-1:${TODAY}`, "{}");
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => {
    root.render(
      <AuthProvider>
        <ToastProvider>
          <RoundTimerProvider>
            <TodaySessionPanel state={contactDay()} structuredPlan={null} token="" onRefresh={async () => {}} />
          </RoundTimerProvider>
        </ToastProvider>
      </AuthProvider>,
    );
  });
  assert.equal(timersOnScreen(), 1);
  assert.match(document.querySelector(".st-mini")?.textContent ?? "", /Rounds/);

  await act(async () => root.unmount());
  container.remove();
  window.localStorage.clear();
});

test("a run saved on an earlier training day never blocks the round timer", async () => {
  window.localStorage.clear();
  window.localStorage.setItem(`${CONTACT_RUN_KEY_PREFIX}plan-1:2000-01-01`, "{}");
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => {
    root.render(
      <RoundTimerProvider>
        <TimerPage />
      </RoundTimerProvider>,
    );
  });
  const start = [...container.querySelectorAll("button")].find((b) => b.textContent === "Start round timer");
  assert.ok(start);
  await act(async () => start.click());
  assert.equal(timersOnScreen(), 1);

  await act(async () => root.unmount());
  container.remove();
  window.localStorage.clear();
});
