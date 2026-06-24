import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import {
  TODAY_EMPTY_TEXT,
  TODAY_EMPTY_TITLE,
  buildTodayCheckinPayload,
  completionRequiresModificationReason,
  completionRequiresReviewFields,
  canCompleteTodaySession,
  getCompletionActions,
  getRecommendationCopy,
  getTodayDecisionBanner,
  getVisibleRiskWatch,
  hasActivePlan,
  hasTodaySession,
  shouldShowTodayCheckin,
} from "./today.ts";
import { submitTodayCheckin, submitTodaySessionCompletion } from "./api.ts";
import type { TodayCommandView } from "./types.ts";

process.env.NEXT_PUBLIC_API_DEBUG = "false";

const BASE_STATE: TodayCommandView = {
  active_plan: { id: "11111111-1111-1111-1111-111111111111", name: "Camp", phase: "SPP" },
  today: {
    training_day: "2026-06-18",
    recommendation_state: "not_checked_in",
    recommendation_reason: null,
    next_session: { session_id: "sess-1", weekday: "Thu", status: "Hard day" },
    session_scope: "today",
    session_label: "Today's session",
    completion_status: "not_started",
  },
  risk_watch: [],
  open_injuries: [],
  week_summary: {},
  quick_actions: [],
};

function installFetchMock(responseBody: unknown) {
  const calls: Array<{ input: string; init?: RequestInit }> = [];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    calls.push({ input: String(input), init });
    return new Response(JSON.stringify(responseBody), {
      status: 201,
      headers: { "content-type": "application/json" },
    });
  }) as typeof fetch;
  return {
    calls,
    restore: () => {
      globalThis.fetch = originalFetch;
    },
  };
}

test("no active plan state uses intake copy and no plan identity", () => {
  assert.equal(TODAY_EMPTY_TITLE, "No active plan yet");
  assert.equal(TODAY_EMPTY_TEXT, "Complete intake to generate your training plan.");
  assert.equal(hasActivePlan({}), false);
});

test("active plan without check-in shows the check-in module rule", () => {
  assert.equal(shouldShowTodayCheckin(BASE_STATE), true);
  assert.equal(
    shouldShowTodayCheckin({
      ...BASE_STATE,
      today: { ...BASE_STATE.today, recommendation_state: "modify" },
    }),
    false,
  );
});

test("decision banner is hidden before check-in", () => {
  assert.equal(getTodayDecisionBanner("not_checked_in"), null);
});

test("decision banner gives command-like copy for each checked-in state", () => {
  assert.deepEqual(getTodayDecisionBanner("train_as_planned"), {
    state: "train_as_planned",
    title: "TRAIN AS PLANNED",
    detail: "Readiness is acceptable. Complete today's prescribed session.",
    tone: "green",
  });
  assert.deepEqual(getTodayDecisionBanner("modify"), {
    state: "modify",
    title: "MODIFY SESSION",
    detail: "Use the safer version today. Remove high-impact work and keep output controlled.",
    tone: "amber",
  });
  assert.deepEqual(getTodayDecisionBanner("pull_back"), {
    state: "pull_back",
    title: "PULL BACK TODAY",
    detail: "Reduce load and intensity. Keep the session technical. Stop if pain rises.",
    tone: "red",
  });
});

test("decision banner prefers the backend readiness reason when present", () => {
  const banner = getTodayDecisionBanner("pull_back", "Sleep was poor and pain is high today.");
  assert.equal(banner?.title, "PULL BACK TODAY");
  assert.equal(banner?.detail, "Sleep was poor and pain is high today.");
  assert.equal(banner?.tone, "red");
});

test("check-in payload does not include a frontend recommendation", () => {
  const payload = buildTodayCheckinPayload({
    planId: "11111111-1111-1111-1111-111111111111",
    phase: "TAPER",
    sleep: "poor",
    body: "flat",
    pain: "manageable",
    safetyFlags: {
      sharp_pain: false,
      instability: false,
      swelling: false,
      neurological_symptoms: false,
      illness_symptoms: false,
      cannot_warm_into_movement: false,
      worse_next_day_pain: false,
    },
  });

  assert.equal(payload.phase, "TAPER");
  assert.equal("recommendation_state" in payload, false);
});

test("active plan in TAPER sends TAPER in the check-in payload", () => {
  const state: TodayCommandView = {
    ...BASE_STATE,
    active_plan: { ...BASE_STATE.active_plan, phase: "TAPER" },
  };
  const payload = buildTodayCheckinPayload({
    planId: state.active_plan.id ?? "",
    phase: state.active_plan.phase,
    sleep: "poor",
    body: "flat",
    pain: "manageable",
    safetyFlags: {
      sharp_pain: false,
      instability: false,
      swelling: false,
      neurological_symptoms: false,
      illness_symptoms: false,
      cannot_warm_into_movement: false,
      worse_next_day_pain: false,
    },
  });

  assert.equal(payload.phase, "TAPER");
});

test("missing phase does not silently default an active plan check-in to GPP", () => {
  assert.throws(
    () =>
      buildTodayCheckinPayload({
        planId: "11111111-1111-1111-1111-111111111111",
        phase: undefined,
        sleep: "poor",
        body: "flat",
        pain: "manageable",
        safetyFlags: {
          sharp_pain: false,
          instability: false,
          swelling: false,
          neurological_symptoms: false,
          illness_symptoms: false,
          cannot_warm_into_movement: false,
          worse_next_day_pain: false,
        },
      }),
    /phase is unavailable/,
  );
});

test("recommendation copy maps valid backend states", () => {
  assert.equal(getRecommendationCopy("train_as_planned").label, "Train as planned");
  assert.equal(getRecommendationCopy("modify").label, "Modify");
  assert.equal(getRecommendationCopy("pull_back").label, "Pull back");
  assert.match(getRecommendationCopy("pull_back").actionText, /Reduce load today/);
});

test("session empty and completion action states are mapped", () => {
  assert.equal(hasTodaySession({}), false);
  assert.deepEqual(getCompletionActions("not_started"), ["Start session", "Mark skipped"]);
  assert.deepEqual(getCompletionActions("started"), ["Resume session", "Mark done", "Mark modified", "Mark skipped"]);
});

test("session details without session_id are visible but not completable", () => {
  const session = { weekday: "Thu", status: "Hard day" };
  assert.equal(hasTodaySession(session), true);
  assert.equal(canCompleteTodaySession(session), false);
  assert.equal(canCompleteTodaySession({ ...session, session_id: "sess-1" }), true);
});

test("off-day entries with no load are not completable even with a session_id", () => {
  const offDay = { session_id: "2026-06-18", weekday: "Thu", effective_load: "none" };
  assert.equal(hasTodaySession(offDay), true);
  assert.equal(canCompleteTodaySession(offDay), false);
  // A real training load keeps the session completable.
  assert.equal(canCompleteTodaySession({ ...offDay, effective_load: "hard" }), true);
});

test("check-in payload carries reported injury and previous-session truth", () => {
  const payload = buildTodayCheckinPayload({
    planId: "11111111-1111-1111-1111-111111111111",
    phase: "SPP",
    sleep: "good",
    body: "normal",
    pain: "none",
    activeInjury: "worse",
    previousSession: "very_hard",
    safetyFlags: {
      sharp_pain: false,
      instability: false,
      swelling: false,
      neurological_symptoms: false,
      illness_symptoms: false,
      cannot_warm_into_movement: false,
      worse_next_day_pain: false,
    },
  });

  assert.equal(payload.active_injury, "worse");
  assert.equal(payload.previous_session, "very_hard");
});

test("check-in payload defaults injury and previous-session to none", () => {
  const payload = buildTodayCheckinPayload({
    planId: "11111111-1111-1111-1111-111111111111",
    phase: "GPP",
    sleep: "good",
    body: "normal",
    pain: "none",
    safetyFlags: {
      sharp_pain: false,
      instability: false,
      swelling: false,
      neurological_symptoms: false,
      illness_symptoms: false,
      cannot_warm_into_movement: false,
      worse_next_day_pain: false,
    },
  });

  assert.equal(payload.active_injury, "none");
  assert.equal(payload.previous_session, "none");
});

test("modified requires a reason and done/modified require review fields", () => {
  assert.equal(completionRequiresModificationReason("modified"), true);
  assert.equal(completionRequiresModificationReason("done"), false);
  assert.equal(completionRequiresReviewFields("done"), true);
  assert.equal(completionRequiresReviewFields("modified"), true);
  assert.equal(completionRequiresReviewFields("skipped"), false);
});

test("risk watch shows icon label text records with overflow count", () => {
  const { visible, overflow } = getVisibleRiskWatch([
    { category: "stop_red_flag", priority: 1, icon: "octagon-x", label: "Stop", text: "Pull back.", tone: "stop" },
    { category: "fatigue", priority: 6, icon: "battery-low", label: "Fatigue", text: "Poor sleep.", tone: "caution" },
    { category: "high_pain", priority: 3, icon: "alert-triangle", label: "High pain", text: "Pain high.", tone: "warning" },
  ]);

  assert.equal(visible.length, 2);
  assert.equal(visible[0].icon.length > 0, true);
  assert.equal(visible[0].label.length > 0, true);
  assert.equal(visible[0].text.length > 0, true);
  assert.equal(overflow, 1);
});

test("submit check-in calls the Today check-in endpoint", async () => {
  const mock = installFetchMock({
    training_day: "2026-06-18",
    recommendation_state: "modify",
    recommendation_reason: "Poor sleep.",
    triggers: ["poor_sleep"],
  });

  try {
    await submitTodayCheckin("token", {
      plan_id: "11111111-1111-1111-1111-111111111111",
      sleep: "poor",
      body: "normal",
      pain: "none",
      phase: "GPP",
    });

    assert.equal(mock.calls.length, 1);
    assert.equal(mock.calls[0].input.endsWith("/api/today/checkin"), true);
    assert.equal(mock.calls[0].init?.method, "POST");
  } finally {
    mock.restore();
  }
});

test("submit completion calls the Today completion endpoint", async () => {
  const mock = installFetchMock({
    completion_status: "done",
    landing_session_state: "completed",
  });

  try {
    await submitTodaySessionCompletion("token", {
      plan_id: "11111111-1111-1111-1111-111111111111",
      session_id: "sess-1",
      status: "done",
      session_rpe: 7,
      pain_after: 2,
    });

    assert.equal(mock.calls.length, 1);
    assert.equal(mock.calls[0].input.endsWith("/api/today/session-completion"), true);
    assert.equal(mock.calls[0].init?.method, "POST");
  } finally {
    mock.restore();
  }
});

test("Today resolves today's blocks from the shared current-day resolver", () => {
  // Today renders today's exact blocks from the active plan's structured_plan,
  // resolved through the SAME shared resolver Plan Detail uses (resolveCurrentDay
  // + the client-mounted 04:00 training-day hook) so the two screens can never
  // disagree on the current day/session.
  const source = readFileSync(new URL("../components/today-screen.tsx", import.meta.url), "utf8");
  assert.equal(source.includes("resolveCurrentDay"), true);
  assert.equal(source.includes("useTrainingDay"), true);
});

test("Today uses structured titles only for actual structured today sessions", () => {
  const source = readFileSync(new URL("../components/today-screen.tsx", import.meta.url), "utf8");
  assert.equal(
    source.includes("const sessionTitle = hasResolvedDaySessions"),
    true,
  );
  assert.equal(
    source.includes(": getSessionTitle(session);"),
    true,
  );
});

test("injury extra detail is stale only when rewriting to a different type", () => {
  const source = readFileSync(new URL("../components/guided-injury-card.tsx", import.meta.url), "utf8");
  const nullBranch = source.slice(
    source.indexOf("if (!opt) {"),
    source.indexOf("const isSame ="),
  );
  const sameBranch = source.slice(
    source.indexOf("if (isSame) {"),
    source.indexOf("const currentType = injury.injury_type;"),
  );
  const rewriteBranch = source.slice(
    source.indexOf("const currentType = injury.injury_type;"),
    source.indexOf("clearTypeSpecificFields(onUpdate);", source.indexOf("const currentType = injury.injury_type;")),
  );

  assert.equal(nullBranch.includes("flagStaleExtraDetail()"), false);
  assert.equal(sameBranch.includes("flagStaleExtraDetail()"), false);
  assert.equal(rewriteBranch.includes("flagStaleExtraDetail()"), true);
});

test("Today renders only today's session, never the full camp map", () => {
  // Today must scope to today's day only. It reuses the per-session camp-map
  // cards but must NOT mount the full StructuredPlanRenderer (command header,
  // week strip, every day) — that belongs to Plan Detail (/plans/[planId]).
  const source = readFileSync(new URL("../components/today-screen.tsx", import.meta.url), "utf8");
  assert.equal(source.includes("StructuredPlanRenderer"), false);
  assert.equal(source.includes("WeekStrip"), false);
});

test("Today's View full plan action routes to the plan detail camp map", () => {
  const source = readFileSync(new URL("../components/today-screen.tsx", import.meta.url), "utf8");
  assert.equal(source.includes("/plans/${activePlan.id}"), true);
});

test("fatigue level control is backed by a range input for drag interaction", () => {
  const source = readFileSync(new URL("../components/rating-controls.tsx", import.meta.url), "utf8");
  assert.equal(source.includes('className="level-slider-input"'), true);
  assert.equal(source.includes('type="range"'), true);
  assert.equal(source.includes("onPointerDown={selectLevelFromPointer}"), true);
});
