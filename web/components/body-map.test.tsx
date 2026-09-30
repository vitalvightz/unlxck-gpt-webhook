import test from "node:test";
import assert from "node:assert/strict";
import { window } from "./test-dom";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { BodyMap } from "./body-map";

test("head has a visible selectable target in both views and anatomy layers", async () => {
  const host = document.createElement("div"); document.body.appendChild(host);
  const root = createRoot(host); const chosen: string[] = [];
  const render = (side: "front" | "back") => root.render(<BodyMap side={side} selections={[]}
    onSideChange={render} onZoneSelect={(zone) => chosen.push(zone)} />);
  try {
    for (const side of ["front", "back"] as const) {
      await act(async () => render(side));
      for (const layer of ["Muscles", "Joints & bones"]) {
        const toggle = Array.from(host.querySelectorAll("button")).find((button) => button.textContent === layer);
        assert.ok(toggle); await act(async () => toggle.click());
        const head = host.querySelector('[aria-label="Head / Neck"]'); assert.ok(head);
        assert.ok(head.querySelector('path.body-map-zone'));
        assert.ok(head.querySelector('.body-map-zone-joint'));
        await act(async () => head.dispatchEvent(new window.KeyboardEvent("keydown", { key: "Enter", bubbles: true })));
      }
    }
    assert.deepEqual(chosen, ["head", "head", "head", "head"]);
  } finally { await act(async () => root.unmount()); host.remove(); }
});

test("thigh taps select the precise side even with an existing knee injury", async () => {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  const chosen: string[] = [];
  const render = (side: "front" | "back") => root.render(
    <BodyMap side={side} selections={[{ zone: "r_knee", label: "Right knee", severity: "low" }]}
      onZoneSelect={(zone) => chosen.push(zone)} onSideChange={render} />,
  );
  try {
    await act(async () => render("front"));
    assert.equal(host.querySelectorAll("svg").length, 1);
    const quad = host.querySelector('[aria-label="Left quad"]');
    assert.ok(quad);
    await act(async () => quad.dispatchEvent(new window.MouseEvent("click", { bubbles: true })));
    await act(async () => quad.dispatchEvent(new window.KeyboardEvent("keydown", { key: "Enter", bubbles: true })));
    assert.deepEqual(chosen, ["l_quad", "l_quad"]);
    assert.equal(host.querySelector('[aria-label="Right knee"]')?.getAttribute("aria-pressed"), "true");
    const back = Array.from(host.querySelectorAll("button")).find((b) => b.textContent === "Back");
    assert.ok(back);
    await act(async () => back.click());
    assert.equal(host.querySelector("svg")?.getAttribute("aria-label"), "back body map for injury selection");
    const hamstring = host.querySelector('[aria-label="Left hamstring"]');
    assert.ok(hamstring);
    await act(async () => hamstring.dispatchEvent(new window.MouseEvent("click", { bubbles: true })));
    assert.deepEqual(chosen, ["l_quad", "l_quad", "l_ham"]);
    assert.equal(host.querySelector(".body-map-refine"), null);
  } finally {
    await act(async () => root.unmount());
    host.remove();
  }
});

test("anatomy switch exposes joint markers and leaves saved muscles visible", async () => {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  const chosen: string[] = [];
  const button = (label: string) => {
    const found = Array.from(host.querySelectorAll("button")).find((entry) => entry.textContent === label);
    assert.ok(found, label);
    return found;
  };
  try {
    await act(async () => root.render(<BodyMap side="front" selections={[{ zone: "l_quad", label: "Left quad" }]}
      onZoneSelect={(key) => chosen.push(key)} onSideChange={() => {}} />));
    assert.equal(button("Muscles").getAttribute("aria-pressed"), "true");
    assert.equal(host.querySelector('[aria-label="Left knee"]'), null);
    await act(async () => button("Joints & bones").click());
    assert.equal(button("Joints & bones").getAttribute("aria-pressed"), "true");
    assert.equal(host.querySelector('[aria-label="Left quad"]')?.getAttribute("aria-pressed"), "true");
    assert.equal(host.querySelector('[aria-label="Right quad"]'), null);
    assert.ok(host.querySelector('[aria-label="Ribs"]'));
    assert.ok(host.querySelector('[aria-label="Left hand"]'));
    const knee = host.querySelector('[aria-label="Left knee"]');
    assert.ok(knee);
    assert.ok(knee.querySelector(".body-map-zone-joint"));
    await act(async () => knee.dispatchEvent(new window.KeyboardEvent("keydown", { key: " ", bubbles: true })));
    assert.deepEqual(chosen, ["l_knee"]);
    await act(async () => button("Muscles").click());
    assert.equal(host.querySelector('[aria-label="Left knee"]'), null);
    assert.deepEqual(chosen, ["l_knee"]);
  } finally {
    await act(async () => root.unmount());
    host.remove();
  }
});
