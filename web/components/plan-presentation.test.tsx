import test from "node:test";
import assert from "node:assert/strict";
import "./test-dom";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { renderToStaticMarkup } from "react-dom/server";
import { CampDayCard, RedFlagsCard, ActiveNotesCard, SessionCard } from "./structured-plan-renderer";
import { readableExerciseMetrics, selectBlockMetric } from "../lib/structured-plan";
import { strength, mental, recovery, trainingPlan } from "../test/training-plan-fixture";

test("readable prescriptions retain every unit, range, round, rest, load and effort", () => {
  assert.equal(readableExerciseMetrics({ metrics: selectBlockMetric(strength.blocks![1]), rest: "120 s", load: null, effort: null }),
    "4 rounds · 2 min work · 2 min rest");
  assert.equal(readableExerciseMetrics({ metrics: [{ label: "Volume", value: "2-3 × 8 per side" }], rest: "30-60 seconds", load: "15 kg", effort: "RPE 6-7" }),
    "2-3 sets × 8 reps per side · 15 kg · RPE 6-7 · 30-60 sec rest");
  assert.equal(readableExerciseMetrics({ metrics: [{ label: "Duration", value: "3 × 20 seconds" }], rest: null, load: null, effort: null }), "3 sets × 20 sec");
  assert.equal(readableExerciseMetrics({ metrics: [], rest: null, load: null, effort: null }), null);
});

test("plan sessions expose all rows without nested expand controls or embedded players", () => {
  const html = renderToStaticMarkup(<SessionCard session={strength} layout="plan" />);
  assert.equal((html.match(/class="ex-row ex-row-compact"/g) ?? []).length, 4);
  assert.match(html, /4 rounds/);
  assert.match(html, /2 min work/);
  assert.match(html, /40 kg/);
  assert.match(html, /RPE 6/);
  assert.doesNotMatch(html, /Stop for sharp shoulder pain/);
  assert.doesNotMatch(html, /sp-session-toggle|ex-row-body|<iframe|ex-row-type/);
});

test("exercise stop criteria appear only after opening the exercise", async () => {
  const host = document.createElement("div"); document.body.append(host); const root = createRoot(host);
  try {
    await act(async () => root.render(<SessionCard session={strength} layout="plan" />));
    assert.equal(host.querySelector(".ex-row-stop"), null);
    await act(async () => (host.querySelector(".ex-row-toggle") as HTMLButtonElement).click());
    assert.match(document.querySelector(".ex-detail-stop")?.textContent ?? "", /sharp shoulder pain/);
  } finally { await act(async () => root.unmount()); host.remove(); }
});

test("recovery limits and global stop/review actions remain outside disclosures", () => {
  const html = renderToStaticMarkup(<><SessionCard session={recovery} layout="plan" />
    <ActiveNotesCard plan={trainingPlan} /><RedFlagsCard plan={trainingPlan} /></>);
  const host = document.createElement("div"); host.innerHTML = html;
  for (const selector of [".rehab-guide-safety", ".sp-note", ".sp-redflag"]) {
    const node = host.querySelector(selector);
    assert.ok(node, selector); assert.equal(node.closest("details"), null);
  }
  assert.match(html, /No contact training/);
  assert.match(html, /Seek medical review/);
});

test("structured mindset content opens full instructions and progression in focused sheets", async () => {
  const host = document.createElement("div"); document.body.append(host); const root = createRoot(host);
  try {
    await act(async () => root.render(<SessionCard session={mental} layout="plan" />));
    assert.equal(host.querySelector(".sp-mental-steps"), null);
    assert.match(host.textContent ?? "", /12 min/);
    assert.doesNotMatch(host.textContent ?? "", /Stop if the rehearsal causes distress/);
    await act(async () => (host.querySelector(".sp-instructions-open") as HTMLButtonElement).click());
    const sheet = document.querySelector('[role="dialog"]')!;
    assert.equal(sheet.querySelectorAll(".sp-mental-steps li").length, 4);
    assert.match(sheet.textContent ?? "", /Stop if the rehearsal causes distress/);
    await act(async () => (sheet.querySelector(".ex-row-toggle") as HTMLButtonElement).click());
    assert.match(document.body.textContent ?? "", /Repeat the same scenario with a different opponent reaction/);
  } finally { await act(async () => root.unmount()); host.remove(); }
});

test("day toggles survive refreshed data and explicit navigation reopens a closed day", async () => {
  const host = document.createElement("div"); document.body.append(host); const root = createRoot(host);
  const day = trainingPlan.weeks![0].days![2];
  try {
    await act(async () => root.render(<CampDayCard day={day} defaultOpen />));
    const card = host.querySelector("details.cm-day")! as HTMLDetailsElement;
    await act(async () => (card.querySelector("summary") as HTMLElement).click());
    await act(async () => card.dispatchEvent(new Event("toggle")));
    assert.equal(card.open, false);
    await act(async () => root.render(<CampDayCard day={{ ...day }} defaultOpen />));
    assert.equal(card.open, false);
    await act(async () => root.render(<CampDayCard day={day} defaultOpen openRequest={{}} />));
    assert.equal(card.open, true);
  } finally { await act(async () => root.unmount()); host.remove(); }
});
