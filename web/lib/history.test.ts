import test from "node:test";
import assert from "node:assert/strict";

import {
  checkinFlagLabels,
  checkinChips,
  countRecentBy,
  injuryReportedTone,
  isWithinLastDays,
  injurySeverityTone,
  injuryStatusLabel,
  injuryStatusTone,
  recommendationLabel,
  recommendationTone,
  sessionStatusLabel,
  sessionStatusTone,
  daysAgoLabel,
  sparringHeadContactLabel,
  sparringIntensityLabel,
  sparringIntensityTone,
  sparringPlanDifference,
  sparringRoundsLabel,
  sparringWeekNote,
} from "./history.ts";
import type { SparringWindowSummary, TodayCheckinHistoryRecord } from "@/lib/types";

test("session status tones follow the green/amber/red contract", () => {
  assert.equal(sessionStatusTone("done"), "green");
  assert.equal(sessionStatusTone("modified"), "amber");
  assert.equal(sessionStatusTone("skipped"), "red");
  assert.equal(sessionStatusTone("started"), "neutral");
  assert.equal(sessionStatusTone("not_started"), "neutral");
});

test("session status labels are short row labels", () => {
  assert.equal(sessionStatusLabel("done"), "Done");
  assert.equal(sessionStatusLabel("modified"), "Modified");
  assert.equal(sessionStatusLabel("skipped"), "Skipped");
});

test("recommendation tones map train/modify/pull-back to green/amber/red", () => {
  assert.equal(recommendationTone("train_as_planned"), "green");
  assert.equal(recommendationTone("modify"), "amber");
  assert.equal(recommendationTone("pull_back"), "red");
  assert.equal(recommendationTone("not_checked_in"), "neutral");
  assert.equal(recommendationLabel("pull_back"), "Pull back");
});

test("injury severity and status tones", () => {
  assert.equal(injurySeverityTone("mild"), "neutral");
  assert.equal(injurySeverityTone("moderate"), "amber");
  assert.equal(injurySeverityTone("severe"), "red");
  assert.equal(injuryStatusTone("open"), "red");
  assert.equal(injuryStatusTone("monitoring"), "amber");
  assert.equal(injuryStatusTone("resolved"), "green");
  assert.equal(injuryStatusLabel("monitoring"), "Monitoring");
});

function checkin(overrides: Partial<TodayCheckinHistoryRecord> = {}): TodayCheckinHistoryRecord {
  return {
    id: "c1",
    athlete_id: "a1",
    plan_id: "p1",
    training_day: "2026-07-01",
    sleep: "good",
    body: "normal",
    pain: "none",
    phase: "GPP",
    recommendation_state: "train_as_planned",
    ...overrides,
  };
}

test("checkinFlagLabels lists only ticked safety flags", () => {
  assert.deepEqual(checkinFlagLabels(checkin()), []);
  assert.deepEqual(
    checkinFlagLabels(checkin({ sharp_pain: true, swelling: true })),
    ["Sharp pain", "Swelling"],
  );
});

test("checkin chips colour only the answers that need attention", () => {
  assert.deepEqual(checkinChips(checkin()), [
    { label: "Sleep good", tone: "neutral" },
    { label: "Body normal", tone: "neutral" },
    { label: "Pain none", tone: "neutral" },
  ]);
  assert.deepEqual(
    checkinChips(checkin({ sleep: "poor", body: "flat", pain: "high", swelling: true })),
    [
      { label: "Sleep poor", tone: "amber" },
      { label: "Body flat", tone: "amber" },
      { label: "Pain high", tone: "red" },
      { label: "Swelling", tone: "red" },
    ],
  );
  // "Body sharp" is feeling sharp: a good sign, not a warning.
  assert.equal(checkinChips(checkin({ body: "sharp", pain: "manageable" }))[1].tone, "neutral");
  assert.equal(checkinChips(checkin({ pain: "manageable" }))[2].tone, "amber");
});

test("injury trend tone follows its direction", () => {
  assert.equal(injuryReportedTone("worse"), "red");
  assert.equal(injuryReportedTone("improving"), "green");
  assert.equal(injuryReportedTone("ongoing"), "neutral");
  assert.equal(injuryReportedTone(undefined), "neutral");
});

test("recent counts include today back to day 7 only", () => {
  const rows = [
    { day: "2026-10-02", status: "done" },
    { day: "2026-09-26", status: "done" }, // 6 days ago: in
    { day: "2026-09-25", status: "skipped" }, // 7 days ago: out
    { day: "2026-10-01", status: "skipped" },
    { day: "2026-10-03", status: "done" }, // future: out
  ];
  assert.deepEqual(
    countRecentBy(rows, { day: (row) => row.day, key: (row) => row.status, today: "2026-10-02", days: 7 }),
    { done: 2, skipped: 1 },
  );
  assert.equal(isWithinLastDays("2026-09-26", "2026-10-02", 7), true);
  assert.equal(isWithinLastDays("2026-09-25", "2026-10-02", 7), false);
});

test("sparring rounds read as rounds × length", () => {
  assert.equal(sparringRoundsLabel(5, 180), "5 × 3 min");
  assert.equal(sparringRoundsLabel(4, 150), "4 × 2:30");
  assert.equal(sparringRoundsLabel(6, 45), "6 × 45s");
  assert.equal(sparringRoundsLabel(1, null), "1 round");
  assert.equal(sparringRoundsLabel(3, null), "3 rounds");
});

test("sparring plan difference flags only a real mismatch", () => {
  assert.deepEqual(sparringPlanDifference("light", "hard"), {
    label: "Planned light — went hard",
    harder: true,
  });
  assert.deepEqual(sparringPlanDifference("hard", "light"), {
    label: "Planned hard — went light",
    harder: false,
  });
  assert.equal(sparringPlanDifference("technical", "light"), null);
  assert.equal(sparringPlanDifference("hard", "hard"), null);
  assert.equal(sparringPlanDifference("contact", "hard"), null);
  assert.equal(sparringPlanDifference(null, "hard"), null);
});

test("days-ago labels count training days", () => {
  assert.equal(daysAgoLabel("2026-10-02", "2026-10-02"), "Today");
  assert.equal(daysAgoLabel("2026-10-01", "2026-10-02"), "Yesterday");
  assert.equal(daysAgoLabel("2026-09-25", "2026-10-02"), "7 days ago");
  assert.equal(daysAgoLabel("2026-10-03", "2026-10-02"), null);
  assert.equal(daysAgoLabel("garbage", "2026-10-02"), null);
});

const week = (overrides: Partial<SparringWindowSummary> = {}): SparringWindowSummary => ({
  days: 7,
  sessions: 0,
  rounds: 0,
  hard_rounds: 0,
  hard_days: 0,
  heavy_head_contact_sessions: 0,
  rocked_count: 0,
  ...overrides,
});

test("sparring week note: rocked first, then over the hard-day cap", () => {
  assert.equal(sparringWeekNote(week({ hard_days: 2 })), null);
  assert.match(sparringWeekNote(week({ hard_days: 3 })) ?? "", /^3 hard sparring days in the last 7/);
  assert.match(sparringWeekNote(week({ hard_days: 4, rocked_count: 1 })) ?? "", /rocked or dropped/);
});

test("sparring tones: hard is amber, everything else neutral", () => {
  assert.equal(sparringIntensityTone("hard"), "amber");
  assert.equal(sparringIntensityTone("medium"), "neutral");
  assert.equal(sparringIntensityLabel("light"), "Light");
  assert.equal(sparringHeadContactLabel("heavy"), "Heavy head contact");
});
