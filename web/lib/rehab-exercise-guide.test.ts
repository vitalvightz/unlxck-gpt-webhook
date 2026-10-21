import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { getRehabExerciseGuide } from "./rehab-exercise-guide";
import type { StructuredBlock } from "./types";

const fixtures = JSON.parse(readFileSync("e2e/fixtures/rehab-bank-publication.json", "utf8"));
const achilles: StructuredBlock = fixtures.achilles_tendonitis.view.live_prescription.session.blocks[0];

test("the actual Achilles prescription becomes three source steps and exact prominent values", () => {
  const before = structuredClone(achilles);
  const guide = getRehabExerciseGuide(achilles);
  assert.deepEqual(guide.metrics, [{ label: "Hold", value: "10s" }, { label: "Reps", value: "10" }, { label: "Frequency", value: "Daily" }]);
  assert.equal(guide.steps.length, 3);
  assert.match(guide.steps[0], /^Sit on the floor/);
  assert.match(guide.steps[1], /^Gently press your toes/);
  assert.match(guide.steps[2], /^Hold for 10 seconds/);
  for (const step of guide.steps) assert.ok(achilles.instructions!.includes(step));
  assert.equal(guide.safety.filter(s => /^Stop if (?:pain or )?symptoms/i.test(s)).length, 1);
  assert.equal(guide.safety.filter(s => /^Follow .*clinician restrictions/i.test(s)).length, 1);
  for (const restriction of achilles.mandatory_restrictions!) assert.ok(guide.safety.includes(restriction));
  assert.deepEqual(achilles, before);
});

test("self-paced content never inherits a number from the bank or stale presentation fields", () => {
  const guide = getRehabExerciseGuide({ ...achilles, dose: {}, sets: 20, reps: 50,
    duration: { value: 600, unit: "seconds" }, drill_snapshot: { ...achilles.drill_snapshot, dose: { sets: 30, reps: 100 } } });
  assert.equal(guide.selfPaced, true);
  assert.deepEqual(guide.metrics, [{ label: "Frequency", value: "Daily" }]);
});

test("missing information does not create a dose or assume self-paced permission", () => {
  assert.deepEqual(getRehabExerciseGuide({}).metrics, []);
  assert.equal(getRehabExerciseGuide({}).selfPaced, false);
});

test("sentence splitting preserves decimals, conditional setup and source wording", () => {
  const source = "When permitted, hold a 0.5 kg weight. Keep the elbow supported. Stop for tingling, sudden pain or loss of function. Seek urgent review if symptoms persist.";
  const guide = getRehabExerciseGuide({ instructions: source });
  assert.deepEqual(guide.steps, ["When permitted, hold a 0.5 kg weight.", "Keep the elbow supported."]);
  assert.deepEqual(guide.safety, ["Stop for tingling, sudden pain or loss of function.", "Seek urgent review if symptoms persist."]);
  assert.equal(guide.metrics.length, 0); // prose is never turned into a measured dose
});

test("different timings, escalation and restrictions survive repeated-warning consolidation", () => {
  const guide = getRehabExerciseGuide({ instructions: "Sit comfortably. Stop if symptoms worsen during or after the work. Follow clinician restrictions.",
    stop_rules: ["Stop if pain or symptoms increase during or after the exercise. Follow your existing clinician restrictions.",
      "Stop if next-day pain increases.", "Stop and seek review if symptoms worsen during or after the work.", "No weight, step or forced range."],
    mandatory_restrictions: ["No weight, step or forced range.", "No training or contact clearance."] });
  assert.equal(guide.safety.length, 6);
  assert.ok(guide.safety.includes("Stop if pain or symptoms increase during or after the exercise."));
  assert.ok(guide.safety.includes("Stop if next-day pain increases."));
  assert.ok(guide.safety.includes("Stop and seek review if symptoms worsen during or after the work."));
  assert.ok(guide.safety.includes("No training or contact clearance."));
});

test("legacy cues and approved ranges remain readable without a separate content model", () => {
  const guide = getRehabExerciseGuide({ coaching_cues: ["Sit with your arm supported. Slowly raise your wrist."],
    mandatory_restrictions: ["no_forceful_grip_speed_forced_range_or_automatic_increase"],
    sets: 2, reps: "8–10" });
  assert.deepEqual(guide.steps, ["Sit with your arm supported.", "Slowly raise your wrist."]);
  assert.deepEqual(guide.metrics, [{ label: "Reps", value: "8–10" }, { label: "Sets", value: "2" }]);
  assert.deepEqual(guide.safety, ["No forceful grip, speed, forced range or automatic increase."]);
});

test("regional pain repeats consolidate only when the broader explicit stop exists", () => {
  const regional = ["Stop if groin pain increases during or after the exercise.", "Stop if elbow pain increases during or after the exercise."];
  assert.deepEqual(getRehabExerciseGuide({ stop_rules: regional }).safety, regional);
  const guide = getRehabExerciseGuide({ stop_rules: [...regional,
    "Stop if pain or symptoms increase during or after the exercise.", "Stop if next-day groin pain increases."] });
  assert.deepEqual(guide.safety, ["Stop if pain or symptoms increase during or after the exercise.", "Stop if next-day groin pain increases."]);
});
