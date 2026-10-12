import assert from "node:assert/strict";
import test from "node:test";
import { window } from "./test-dom";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { ExercisePrescriptionEditor } from "./exercise-prescription-editor";
import type { ExerciseChangeDose } from "@/lib/types";
import type { ExerciseCoaching } from "./exercise-prescription-editor";

test("hill runs show work and rounds, then submit editable rest instead of sets and reps", async () => {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  let result: ExerciseChangeDose | undefined;
  try {
    await act(async () => root.render(<ExercisePrescriptionEditor initial={{ mode: "intervals", rounds: 6, work_seconds: 20 }}
      action="Add" busy={false} onSubmit={dose => { result = dose; }} />));
    assert.equal(host.querySelector('[aria-label="Sets"]'), null);
    assert.equal(host.querySelector('[aria-label="Reps"]'), null);
    assert.equal(host.querySelector<HTMLInputElement>('[aria-label="Work"]')!.value, "20");
    const submit = host.querySelector<HTMLButtonElement>('button[type="submit"]')!;
    assert.equal(submit.disabled, true);
    const rest = host.querySelector<HTMLInputElement>('[aria-label="Rest"]')!;
    await act(async () => {
      Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value")!.set!.call(rest, "60");
      rest.dispatchEvent(new window.Event("input", { bubbles: true }));
    });
    assert.equal(submit.disabled, false);
    await act(async () => host.querySelector("form")!.dispatchEvent(new window.Event("submit", { bubbles: true, cancelable: true })));
    assert.equal(result?.mode, "intervals");
    assert.equal(result?.rest_seconds, 60);
  } finally {
    await act(async () => root.unmount());
    host.remove();
  }
});


test("existing exercise coaching fields stay collapsed until the disclosure is opened", async () => {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  try {
    await act(async () => root.render(<ExercisePrescriptionEditor
      initial={{ mode: "reps", sets: 3, reps: 8 }} action="Save changes" busy={false}
      coaching={{ coaching_cues: ["Brace"], regression_options: [], progression_rule: null, stop_rules: ["Stop for sharp pain"] }}
      onSubmit={() => {}} />));
    const advanced = host.querySelector<HTMLDetailsElement>("details")!;
    assert.equal(advanced.open, false);
    await act(async () => advanced.querySelector("summary")!.click());
    assert.equal(advanced.open, true);
  } finally {
    await act(async () => root.unmount());
    host.remove();
  }
});


test("an edited card submits Easier and Progress alongside cues and stop rules, and an emptied Progress clears", async () => {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  let result: ExerciseCoaching | undefined;
  const type = async (label: string, value: string) => {
    const field = host.querySelector<HTMLTextAreaElement>(`[aria-label="${label}"]`)!;
    await act(async () => {
      Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value")!.set!.call(field, value);
      field.dispatchEvent(new window.Event("input", { bubbles: true }));
    });
  };
  try {
    await act(async () => root.render(<ExercisePrescriptionEditor
      initial={{ mode: "reps", sets: 3, reps: 8 }} action="Save changes" busy={false}
      coaching={{ coaching_cues: ["Brace"], regression_options: ["Box squat"], progression_rule: "Add 2 reps", stop_rules: [] }}
      onSubmit={(_dose, coaching) => { result = coaching; }} />));
    // Per side sits with the reps, outside the folds.
    assert.equal(host.querySelector('details [aria-label="Per side"]'), null);
    assert.equal(host.querySelector<HTMLTextAreaElement>('[aria-label="Easier"]')!.value, "Box squat");
    await type("Easier", "Box squat\n\n Wall sit ");
    await type("Progress", "  ");
    await act(async () => host.querySelector("form")!.dispatchEvent(new window.Event("submit", { bubbles: true, cancelable: true })));
    assert.deepEqual(result, { coaching_cues: ["Brace"], regression_options: ["Box squat", "Wall sit"], progression_rule: "", stop_rules: [] });
  } finally {
    await act(async () => root.unmount());
    host.remove();
  }
});
