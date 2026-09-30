import test from "node:test";
import assert from "node:assert/strict";
import { window } from "./test-dom";
import { act, useState } from "react";
import { createRoot } from "react-dom/client";
import { GuidedInjuryCard } from "./guided-injury-card";
import { EMPTY_GUIDED_INJURY, buildGuidedInjuryFields, type GuidedInjuryState } from "@/lib/guided-injury";

test("onboarding records tap choices without typing and collapses a complete injury", async () => {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  let saved: GuidedInjuryState | undefined;
  function Editor() {
    const [injury, setInjury] = useState({ ...EMPTY_GUIDED_INJURY, area: "Left shoulder", zone: "l_shoulder", notes: "[red_flags:none]" });
    const [active, setActive] = useState(true);
    return <GuidedInjuryCard injury={injury} index={0} isActive={active} onRemove={() => {}}
      onUpdate={(key, value) => setInjury((current) => ({ ...current, [key]: value }))}
      onToggleActive={() => { saved = injury; setActive(!active); }} />;
  }
  async function press(label: string) {
    const button = Array.from(host.querySelectorAll("button")).find((node) => node.textContent?.trim() === label);
    assert.ok(button, label);
    await act(async () => button.click());
  }
  try {
    await act(async () => root.render(<Editor />));
    assert.equal(host.querySelector("input, textarea"), null);
    assert.equal((host.textContent?.match(/Left shoulder/g) ?? []).length, 1);
    assert.equal(host.querySelector('button button, [role="button"] button'), null);
    await press("Tightness");
    await press("Limiting me");
    await press("→ Stable");
    await press("Save injury");
    assert.equal(host.querySelector(".injury-card-form"), null);
    assert.match(host.textContent ?? "", /Tightness · Limiting me/);
    assert.equal((host.textContent?.match(/Limiting me/g) ?? []).length, 1);
    assert.equal((host.textContent?.match(/Stable/g) ?? []).length, 1);
    assert.equal(host.querySelector(".injury-card-badges"), null);
    assert.ok(saved);
    const fields = buildGuidedInjuryFields([saved]);
    assert.equal(fields.guided_injuries[0].severity, "moderate");
    assert.equal(fields.guided_injuries[0].zone, "l_shoulder");
    assert.match(fields.guided_injuries[0].notes, /\[red_flags:none\]/);
    assert.match(fields.guided_injuries[0].notes, /\[training_impact:limiting\]/);
    await press("Edit");
    assert.equal(host.querySelector("input, textarea"), null);
  } finally { await act(async () => root.unmount()); host.remove(); }
});


test("map-first mode hides questions and manual entry reveals only the location field", async () => {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  function Editor() {
    const [injury, setInjury] = useState({ ...EMPTY_GUIDED_INJURY });
    const [picking, setPicking] = useState(true);
    return <GuidedInjuryCard injury={injury} index={0} isActive locationOnly={picking}
      onManualEntry={() => setPicking(false)} onToggleActive={() => {}} onRemove={() => {}}
      onUpdate={(key, value) => setInjury((current) => ({ ...current, [key]: value }))} />;
  }
  try {
    await act(async () => root.render(<Editor />));
    assert.equal(host.querySelector("input, textarea, .injury-card-form"), null);
    assert.doesNotMatch(host.textContent ?? "", /Injury type|Current trend|How much/);
    const manual = host.querySelector<HTMLButtonElement>(".injury-manual-entry");
    assert.ok(manual);
    await act(async () => manual.click());
    const input = host.querySelector<HTMLInputElement>("input");
    assert.ok(input);
    assert.equal(document.activeElement, input);
    assert.doesNotMatch(host.textContent ?? "", /Injury type|Current trend|How much/);
    await act(async () => {
      Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value")!.set!.call(input, "Left wrist");
      input.dispatchEvent(new window.Event("input", { bubbles: true }));
    });
    assert.match(host.textContent ?? "", /Injury type/);
    assert.match(host.textContent ?? "", /How much is it affecting you/);
    assert.equal(host.querySelector<HTMLButtonElement>(".gi-save-injury")?.disabled, true);
  } finally { await act(async () => root.unmount()); host.remove(); }
});

test("safety follow-ups still block saving until required answers are supplied", async () => {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  function Editor() {
    const [injury, setInjury] = useState<GuidedInjuryState>({ ...EMPTY_GUIDED_INJURY,
      area: "Head / Neck", zone: "head", injury_type: "head_impact", severity: "high", trend: "stable",
      notes: "[training_impact:cant_train]" });
    return <GuidedInjuryCard injury={injury} index={0} isActive onToggleActive={() => {}} onRemove={() => {}}
      onUpdate={(key, value) => setInjury((current) => ({ ...current, [key]: value }))} />;
  }
  try {
    await act(async () => root.render(<Editor />));
    assert.match(host.textContent ?? "", /Red-flag checklist/);
    assert.equal(host.querySelector<HTMLButtonElement>(".gi-save-injury")?.disabled, true);
    const none = Array.from(host.querySelectorAll("button")).find((button) => button.textContent === "None of these");
    assert.ok(none);
    await act(async () => none.click());
    assert.equal(host.querySelector<HTMLButtonElement>(".gi-save-injury")?.disabled, false);
    const remove = host.querySelector<HTMLButtonElement>('[aria-label="Remove injury 1"]');
    assert.ok(remove);
    assert.equal(remove.closest('[role="button"]'), null);
  } finally { await act(async () => root.unmount()); host.remove(); }
});
