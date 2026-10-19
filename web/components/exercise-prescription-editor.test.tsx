import assert from "node:assert/strict";
import test from "node:test";
import { window } from "./test-dom";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { ExercisePrescriptionEditor } from "./exercise-prescription-editor";
import type { ExerciseChangeDose } from "@/lib/types";
import type { ExerciseLogActual } from "@/lib/api-schema.generated";
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


test("sets × reps weight is a number with a picked unit, and the pencil switches to free text", async () => {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  const results: ExerciseChangeDose[] = [];
  const set = async (selector: string, value: string, proto: typeof window.HTMLInputElement | typeof window.HTMLSelectElement = window.HTMLInputElement) => {
    const field = host.querySelector<HTMLInputElement>(selector)!;
    await act(async () => {
      Object.getOwnPropertyDescriptor(proto.prototype, "value")!.set!.call(field, value);
      field.dispatchEvent(new window.Event(proto === window.HTMLSelectElement ? "change" : "input", { bubbles: true }));
    });
  };
  const submit = () => act(async () => host.querySelector("form")!.dispatchEvent(new window.Event("submit", { bubbles: true, cancelable: true })));
  try {
    await act(async () => root.render(<ExercisePrescriptionEditor initial={{ mode: "reps", sets: 3, reps: 8 }}
      action="Add" busy={false} past={{ id: "key:goblet-squat", name: "Goblet Squat", identity_kind: "canonical", latest_day: "2026-10-12",
        latest_values: { load: { value: 25, unit: "kg" } } as ExerciseLogActual, latest_confirmed_as_prescribed: false, best_loads: [] }} onSubmit={dose => { results.push(dose); }} />));
    assert.equal(host.querySelector<HTMLInputElement>('[aria-label="Weight"]')!.placeholder, "25");
    assert.equal(host.querySelector<HTMLSelectElement>('[aria-label="Weight unit"]')!.value, "kg");
    await set('[aria-label="Weight"]', "30");
    await submit();
    assert.equal(results.at(-1)?.load_or_intensity, "30 kg");
    await set('[aria-label="Weight unit"]', "lb", window.HTMLSelectElement);
    await submit();
    assert.equal(results.at(-1)?.load_or_intensity, "30 lb");
    await act(async () => host.querySelector<HTMLButtonElement>('[aria-label="Describe it instead of a weight"]')!.click());
    assert.equal(host.querySelector('[aria-label="Weight"]'), null);
    await set('[aria-label="Intensity"]', "fast");
    await submit();
    assert.equal(results.at(-1)?.load_or_intensity, "fast");
  } finally {
    await act(async () => root.unmount());
    host.remove();
  }
});

test("timed work and existing text open on free text, an existing weight opens on the number", async () => {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  try {
    await act(async () => root.render(<ExercisePrescriptionEditor initial={{ mode: "duration", duration_seconds: 60 }}
      action="Add" busy={false} onSubmit={() => {}} />));
    assert.ok(host.querySelector('[aria-label="Intensity"]'));
    await act(async () => root.render(<ExercisePrescriptionEditor key="text" initial={{ mode: "reps", sets: 3, reps: 8, load_or_intensity: "Bodyweight" }}
      action="Add" busy={false} onSubmit={() => {}} />));
    assert.equal(host.querySelector<HTMLInputElement>('[aria-label="Intensity"]')!.value, "Bodyweight");
    await act(async () => root.render(<ExercisePrescriptionEditor key="weight" initial={{ mode: "distance", distance: 20, distance_unit: "m", load_or_intensity: "24kg" }}
      action="Add" busy={false} onSubmit={() => {}} />));
    assert.equal(host.querySelector<HTMLInputElement>('[aria-label="Weight"]')!.value, "24");
  } finally {
    await act(async () => root.unmount());
    host.remove();
  }
});
