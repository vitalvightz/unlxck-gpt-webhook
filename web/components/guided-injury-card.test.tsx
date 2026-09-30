import test from "node:test";
import assert from "node:assert/strict";
import "./test-dom";
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
    await press("Tightness");
    await press("Limiting me");
    await press("→ Stable");
    await press("Save injury");
    assert.equal(host.querySelector(".injury-card-form"), null);
    assert.match(host.textContent ?? "", /Tightness · Limiting me/);
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
