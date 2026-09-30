import test from "node:test";
import assert from "node:assert/strict";
import { window } from "./test-dom";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { BodyMap } from "./body-map";

test("one body view exposes muscles and joints through nearby-area refinement", async () => {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  const chosen: string[] = [];
  const render = (side: "front" | "back") => root.render(
    <BodyMap side={side} selections={[{ zone: "l_knee", label: "Left knee", severity: "low" }]}
      onZoneSelect={(zone) => chosen.push(zone)} onSideChange={render} />,
  );
  try {
    await act(async () => render("front"));
    assert.equal(host.querySelectorAll("svg").length, 1);
    assert.doesNotMatch(host.textContent ?? "", /Muscles|Joints & bones|severity/);
    const leg = host.querySelector('[aria-label="Left thigh / knee"]');
    assert.ok(leg);
    await act(async () => leg.dispatchEvent(new window.KeyboardEvent("keydown", { key: "Enter", bubbles: true })));
    const knee = Array.from(host.querySelectorAll("button")).find((b) => b.textContent === "Left knee");
    assert.ok(knee);
    assert.equal(knee.getAttribute("aria-pressed"), "true");
    await act(async () => knee.click());
    await act(async () => knee.click());
    assert.deepEqual(chosen, ["l_knee", "l_knee"]);
    const back = Array.from(host.querySelectorAll("button")).find((b) => b.textContent === "Back");
    assert.ok(back);
    await act(async () => back.click());
    assert.equal(host.querySelector("svg")?.getAttribute("aria-label"), "back body map for injury selection");
    assert.equal(host.querySelector(".body-map-refine"), null);
    assert.ok(host.querySelector('[aria-label="Left lower leg / foot"]'));
  } finally {
    await act(async () => root.unmount());
    host.remove();
  }
});
