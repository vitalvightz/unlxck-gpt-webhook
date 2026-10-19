import assert from "node:assert/strict";
import test from "node:test";
import type { PersonalExercise } from "./api-schema.generated";
import { exerciseResult } from "./exercise-library";

const exercise = (changes: Partial<PersonalExercise> = {}) => ({ id: "key:squat", name: "Squat", identity_kind: "canonical",
  latest_day: "2026-10-19", latest_values: {}, latest_confirmed_as_prescribed: false, best_loads: [], ...changes }) as PersonalExercise;

test("best recorded kg and lb remain separate and legacy results make no cross-date PR claim", () => {
  const best_loads = [{ value: 100, unit: "kg", basis: "reported" }, { value: 200, unit: "lb", basis: "reported" }] as PersonalExercise["best_loads"];
  assert.deepEqual(exerciseResult(exercise({ best_loads })), { label: "Best recorded loads · by unit", value: "100 kg · 200 lb" });
  assert.equal(exerciseResult(exercise({ best_loads, identity_kind: "legacy" })).label, "Recorded load");
});

test("bodyweight, duration and interval results do not require a weight or fabricate a best", () => {
  assert.equal(exerciseResult(exercise({ latest_values: { sets: 3, reps: 15 } as PersonalExercise["latest_values"] })).value, "3 × 15");
  assert.equal(exerciseResult(exercise({ latest_values: { duration: { value: 120, unit: "seconds" } } as PersonalExercise["latest_values"] })).value, "2 min");
  assert.equal(exerciseResult(exercise({ latest_values: { rounds: 6 } as PersonalExercise["latest_values"] })).value, "6 rounds");
  assert.deepEqual(exerciseResult(exercise({ latest_confirmed_as_prescribed: true })), { label: "Latest confirmed", value: "Completed as prescribed" });
});
