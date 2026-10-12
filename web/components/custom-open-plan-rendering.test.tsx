import assert from "node:assert/strict";
import test from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { ExerciseRow, StructuredPlanRenderer } from "./structured-plan-renderer";
import { ExerciseMediaProvider } from "./exercise-demo";
import { PrivateExerciseMediaProvider } from "./private-exercise-video";
import type { StructuredBlock, StructuredPlan, StructuredDay } from "../lib/types";

const block: StructuredBlock = {
  block_id: "my-squat", block_type: "strength", display_name: "My squat",
  prescription_source: "athlete", sets: 3, reps: 5, rest: { value: 90, unit: "seconds" },
  prescription_text: "3 × 5 · 80 kg · rest 90s · tempo 3-1-X · per side",
  notes: "Use my rack",
};

test("the shared Enhanced Card renders the exact athlete dose and only available coaching", () => {
  const html = renderToStaticMarkup(<ExerciseRow block={block} open onToggle={() => {}} />);
  assert.match(html, /My squat/);
  assert.match(html, /80 kg/);
  assert.match(html, /rest 90s/);
  assert.match(html, /tempo 3-1-X/);
  assert.match(html, /Use my rack/);
  assert.doesNotMatch(html, /Why today|Why it|Progress|Easier|Stop rule/);
});

test("catalogue media and private attachments render within the existing exercise row", () => {
  const catalogue = renderToStaticMarkup(
    <ExerciseMediaProvider media={{ "exercise:my-squat": {
      provider: "youtube", video_id: "abcdefghijk", start_s: 0, source: "curated",
    } }}>
      <ExerciseRow block={{ ...block, exercise_key: "my-squat" }} open onToggle={() => {}} />
    </ExerciseMediaProvider>,
  );
  assert.match(catalogue, /Has demo video/);
  const manual = renderToStaticMarkup(
    <PrivateExerciseMediaProvider token="owner-token">
      <ExerciseRow block={{ ...block, private_media_id: "owner-video" }} open onToggle={() => {}} />
    </PrivateExerciseMediaProvider>,
  );
  assert.match(manual, /Opening video/);
  const plain = renderToStaticMarkup(
    <ExerciseMediaProvider media={{ "My squat": {
      provider: "youtube", video_id: "abcdefghijk", start_s: 0, source: "curated",
    } }}>
      <ExerciseRow block={block} open onToggle={() => {}} />
    </ExerciseMediaProvider>,
  );
  assert.doesNotMatch(plain, /Has demo video/); // no guessed manual identity
});

test("custom Open Plans retain the shared weekly navigation and multiple session cards", () => {
  const plan: StructuredPlan = {
    plan_metadata: { title: "My week", plan_type: "open_ongoing_system", prescription_source: "athlete" },
    weeks: [1, 2, 3, 4].map(week => ({
      week_index: week, phase_label: "GPP",
      days: [{ weekday: "Mon", date: `2026-10-${String(12 + (week - 1) * 7).padStart(2, "0")}`,
        today_card: { headline: "Strength and rounds" },
        sessions: [
          { session_id: "strength", prescription_source: "athlete", title: "Strength", session_type: "strength_power", blocks: [block] },
          { session_id: "rounds", prescription_source: "athlete", title: "Rounds", session_type: "conditioning", blocks: [{
            ...block, block_id: "bike", display_name: "My bike", prescription_text: "4 × 30s · rest 0s",
          }] },
        ],
      }],
    })),
  };
  const html = renderToStaticMarkup(<StructuredPlanRenderer plan={plan} openOngoing today={new Date("2026-10-12T12:00:00")} />);
  assert.match(html, /Week 1/);
  assert.match(html, /data-week-pos="3"/);
  assert.match(html, /Strength/);
  assert.match(html, /Rounds/);
  assert.match(html, /saved prescription/);
  assert.doesNotMatch(html, /Cut working volume/);
});


test("optional athlete recovery stays visible without completion counts or retro-log controls", () => {
  const day: StructuredDay = { weekday: "Tue", date: "2026-10-13", day_type: "recovery", today_card: { headline: "Recovery day" },
    sessions: [{ session_id: "recovery", session_type: "recovery", title: "My recovery", prescription_source: "athlete", optional: true,
      blocks: [{ ...block, block_id: "recovery-work", block_type: "cooldown_recovery", display_name: "My mobility" }] }] };
  assert.deepEqual(dayCompletion(day), { done: 0, total: 0 });
  const plan: StructuredPlan = { plan_metadata: { title: "My week", plan_type: "open_ongoing_system", prescription_source: "athlete" },
    weeks: [{ week_index: 1, phase_label: "GPP", days: [day] }] };
  const html = renderToStaticMarkup(<StructuredPlanRenderer plan={plan} openOngoing today={new Date("2026-10-14T12:00:00")}
    completions={[]} currentTrainingDayIso="2026-10-14" onLogSession={() => { throw new Error("Recovery cannot log a workout"); }} />);
  assert.match(html, /My recovery/);
  assert.doesNotMatch(html, /Log session|Missed/);
});
import { dayCompletion } from "../lib/camp-map";
