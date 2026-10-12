import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { renderToStaticMarkup } from "react-dom/server";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { window as domWindow } from "../test-dom";

import { ToastProvider } from "@/components/toast-provider";
import { AuthProvider } from "@/components/auth-provider";
import { TodaySessionPanel } from "@/components/today/today-session-panel";
import { CurrentBlockCard, UpNextCard } from "./home-dashboard";
import { resolveTrainingDay, toISODate } from "@/lib/camp-map";
import { resolveUpNextSummary } from "@/lib/home-up-next";
import type { PlanScheduleContext, StructuredPlan, StructuredSession, TodayCommandView } from "@/lib/types";

// Today resolves its day from the clock once mounted, so the fixture is today.
const TRAINING_DAY = resolveTrainingDay(new Date());
const DAY = toISODate(TRAINING_DAY);

const athleteSessions: StructuredSession[] = [
  {
    session_id: "own-strength",
    title: "Heavy lower",
    session_type: "strength_power",
    prescription_source: "athlete",
    planned_duration: { value: 40, unit: "min" },
    blocks: [
      { block_id: "squat", block_type: "strength", display_name: "Back squat", sets: 5, reps: "5", prescription_source: "athlete" },
      { block_id: "rdl", block_type: "strength", display_name: "Romanian deadlift", sets: 3, reps: "8", prescription_source: "athlete" },
    ],
  },
  {
    session_id: "own-conditioning",
    title: "Bag rounds",
    session_type: "conditioning",
    prescription_source: "athlete",
    planned_duration: { value: 20, unit: "min" },
    blocks: [
      { block_id: "bag", block_type: "conditioning", display_name: "Heavy bag rounds", sets: 6, reps: "3 min", prescription_source: "athlete" },
    ],
  },
];

function athletePlan(): StructuredPlan {
  return {
    plan_metadata: { title: "My plan", plan_type: "open_ongoing_system" },
    weeks: [1, 2, 3, 4].map((index) => ({
      week_index: index,
      days: index === 4 ? [{ date: DAY, sessions: athleteSessions }] : [],
    })),
  } as StructuredPlan;
}

/** The server's live prescription for an athlete-owned day: one combined
 * session whose blocks remember the saved session they came from. */
function athleteLiveState(): TodayCommandView {
  return {
    active_plan: { id: "plan-1", name: "My plan", phase: "GPP" },
    today: {
      training_day: DAY,
      recommendation_state: "train_as_planned",
      decision_tier: "green",
      warnings: [],
      next_session: {
        session_id: "own-strength",
        title: "Heavy lower",
        calendar_date: DAY,
        session_relation: "today",
        // The combined session's own estimate; the parts state 40 + 20 min.
        estimated_duration: 55,
        effective_load: "moderate",
      },
      session_scope: "today",
      session_label: "Today's session",
      completion_status: "not_started",
    },
    live_prescription: {
      revision: "a".repeat(64),
      frozen: false,
      safety_hold: false,
      changes: [],
      session: {
        session_id: "own-strength",
        title: "Heavy lower",
        session_type: "strength_power",
        prescription_source: "athlete",
        blocks: athleteSessions.flatMap((session) =>
          (session.blocks ?? []).map((block) => ({ ...block, source_session_id: session.session_id }))),
      },
    },
    risk_watch: [],
    open_injuries: [],
    week_summary: {},
    quick_actions: [],
  } as TodayCommandView;
}

function chipText(html: string): string[] {
  const holder = domWindow.document.createElement("div");
  holder.innerHTML = html;
  return [...holder.querySelectorAll(".today-session-chips li")].map((chip) => chip.textContent ?? "");
}

test("Home and Today show an athlete-owned live day with the same parts, exercises and time", async () => {
  const plan = athletePlan();
  const state = athleteLiveState();

  const container = domWindow.document.createElement("div");
  domWindow.document.body.append(container);
  const root = createRoot(container);
  await act(async () => {
    root.render(
      <AuthProvider>
        <ToastProvider>
          <TodaySessionPanel state={state} structuredPlan={plan} token="token" onRefresh={async () => {}}
            planSchedule={{ scheduleContext: { current_week_number: 4 } as PlanScheduleContext, createdAt: null }} />
        </ToastProvider>
      </AuthProvider>,
    );
  });
  let today: { title: string; parts: string; chips: string[] };
  try {
    today = {
      title: container.querySelector("#today-session-heading")?.textContent ?? "",
      parts: container.querySelector(".today-session-parts")?.textContent ?? "",
      chips: [...container.querySelectorAll(".today-session-chips li")].map((chip) => chip.textContent ?? ""),
    };
  } finally {
    await act(async () => root.unmount());
    container.remove();
  }

  const upNext = resolveUpNextSummary({
    state,
    structuredPlan: plan,
    trainingDay: TRAINING_DAY,
    openOngoing: true,
    scheduleHints: { currentWeekNumber: 4 },
    policy: null,
  });
  const homeHtml = renderToStaticMarkup(
    <UpNextCard
      dateLabel="Today"
      title={upNext.title}
      subtitle={upNext.subtitle}
      chips={upNext.chips}
      action={{ href: "/today#today-session", label: "Start session" }}
    />,
  );

  // Two saved sessions stay two parts on both screens, never one combined session.
  assert.deepEqual(upNext.sessions.map((session) => session.session_id), ["own-strength", "own-conditioning"]);
  assert.deepEqual(upNext.sessions.map((session) => session.blocks?.length), [2, 1]);
  assert.equal(today.title, "Strength + Conditioning");
  assert.equal(upNext.title, today.title);
  assert.equal(today.parts, "Heavy lower · Bag rounds");
  assert.equal(upNext.subtitle, today.parts);
  // The parts' own minutes (40 + 20), not the combined session's estimate.
  assert.deepEqual(today.chips, ["~About 60 min", "Moderate", "3 exercises"]);
  assert.deepEqual(chipText(homeHtml), today.chips);
});

test("Home's current block never gives week guidance over an athlete's own prescription", () => {
  const generated = renderToStaticMarkup(
    <CurrentBlockCard plan={{ weeks: [1, 2, 3, 4].map((week_index) => ({ week_index, days: [] })) } as StructuredPlan}
      weekNumber={4} trainingDay={new Date(`${DAY}T12:00:00`)} />,
  );
  assert.match(generated, /Cut working volume roughly in half/);

  for (const html of [
    // From the week's saved sessions…
    renderToStaticMarkup(<CurrentBlockCard plan={athletePlan()} weekNumber={4} trainingDay={new Date(`${DAY}T12:00:00`)} />),
    // …or from today's resolved sessions.
    renderToStaticMarkup(
      <CurrentBlockCard plan={{ weeks: [1, 2, 3, 4].map((week_index) => ({ week_index, days: [] })) } as StructuredPlan}
        weekNumber={4} trainingDay={new Date(`${DAY}T12:00:00`)} athletePrescribed />,
    ),
  ]) {
    assert.match(html, /Follow your saved prescription/);
    assert.doesNotMatch(html, /Cut working volume/);
  }
});

test("Home keeps today's restriction whole on Up next", () => {
  const line = "Keep it controlled: skip sparring, no max-effort lifts.";
  const html = renderToStaticMarkup(
    <UpNextCard dateLabel="Today" title="Strength" chips={[]}
      decision={{ chip: "AMBER", tone: "amber", line }}
      action={{ href: "/today#today-session", label: "Start session" }} />,
  );
  assert.ok(html.includes("skip sparring, no max-effort lifts."));

  // The page passes the full action, never a shortened lead.
  const page = readFileSync(new URL("../../app/page.tsx", import.meta.url), "utf8");
  assert.doesNotMatch(page, /directiveLead/);
  assert.match(page, /decisionBanner\.action \|\| decisionBanner\.title/);
});
