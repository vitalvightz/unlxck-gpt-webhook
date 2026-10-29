import test from "node:test";
import assert from "node:assert/strict";
import "./test-dom";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { renderToStaticMarkup } from "react-dom/server";
import { StructuredPlanRenderer, CampDayCard, RedFlagsCard, ActiveNotesCard, SessionCard } from "./structured-plan-renderer";
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

test("recovery limits and active notes stay visible; general red flags fold into one row", () => {
  const html = renderToStaticMarkup(<><SessionCard session={recovery} layout="plan" />
    <ActiveNotesCard plan={trainingPlan} /><RedFlagsCard plan={trainingPlan} /></>);
  const host = document.createElement("div"); host.innerHTML = html;
  for (const selector of [".rehab-guide-safety", ".sp-note"]) {
    const node = host.querySelector(selector);
    assert.ok(node, selector); assert.equal(node.closest("details"), null);
  }
  const redFlags = host.querySelector(".sp-redflag")?.closest("details.sp-redflags") as HTMLDetailsElement | null;
  assert.ok(redFlags); assert.equal(redFlags.open, false);
  assert.match(redFlags.querySelector("summary")?.textContent ?? "", /Red flags - stop & report/);
  assert.match(html, /No contact training/);
  assert.match(html, /Seek medical review/);
});

test("structured mindset content renders its steps and stop rule in full on the plan card", () => {
  const html = renderToStaticMarkup(<SessionCard session={mental} layout="plan" />);
  const host = document.createElement("div"); host.innerHTML = html;
  assert.equal(host.querySelectorAll(".sp-mental-steps li").length, 4);
  assert.match(host.textContent ?? "", /12 min/);
  assert.match(host.textContent ?? "", /Stop if the rehearsal causes distress/);
  assert.equal(host.querySelector(".sp-instructions-open"), null);
  assert.equal(host.querySelector('[role="dialog"]'), null);
});

test("plan mental cards keep the objective and progression inline", () => {
  const host = document.createElement("div");
  host.innerHTML = renderToStaticMarkup(<SessionCard session={mental} layout="plan" />);
  assert.match(host.querySelector(".sp-session-objective")?.textContent ?? "", /Practise recovering your composure/);
  const progression = host.querySelector('[data-kind="progression"]');
  assert.match(progression?.textContent ?? "", /Repeat the same scenario with a different opponent reaction/);
  assert.equal(host.textContent?.split("Repeat the same scenario").length, 2, "printed once");
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

test("single-set prescriptions omit the multiplier for reps and timed work", () => {
  for (const [label, value, expected] of [["Volume", "1 \u00d7 10", "10 reps"], ["Duration", "1 \u00d7 30 seconds", "30 sec"], ["Work", "1 \u00d7 60 seconds", "1 min work"]]) {
    assert.equal(readableExerciseMetrics({ metrics: [{ label, value }], load: null, effort: null, rest: null }), expected);
  }
});

test("Today and the next actionable session retain separate markers", () => {
  const html = renderToStaticMarkup(<StructuredPlanRenderer plan={trainingPlan} today={new Date(2026, 9, 28, 12)}
    focusDay={new Date(2026, 9, 30, 12)} currentDayLabel="Next session" />);
  const host = document.createElement("div"); host.innerHTML = html;
  assert.match(host.querySelector('.cm-day-current')?.textContent ?? "", /Today/);
  assert.match(host.querySelector('.cm-day-next')?.textContent ?? "", /Next session/);
  assert.equal(host.querySelector('.cm-day-next')?.getAttribute('data-day-index'), "3");
});

const notesPlan = (notes: { category: string; text: string }[]) => ({ ...trainingPlan, red_flag_rules: [], plan_notes: notes });

test("Plan notes: informational notes are collapsed by default", () => {
  const host = document.createElement("div");
  host.innerHTML = renderToStaticMarkup(<ActiveNotesCard plan={notesPlan([
    { category: "weight_cut", text: "No weight-cut target is assumed." },
    { category: "conditioning", text: "Aerobic base is built on easy bike work." },
  ])} />);
  const details = host.querySelector("details") as HTMLDetailsElement | null;
  assert.ok(details); assert.equal(details.open, false);
  for (const text of ["No weight-cut target is assumed.", "Aerobic base is built on easy bike work."]) {
    const note = Array.from(host.querySelectorAll(".sp-note-text")).find(node => node.textContent === text);
    assert.ok(note?.closest("details"), `${text} sits behind the disclosure`);
  }
});

test("Plan notes: active restrictions stay visible beside collapsed context", () => {
  const host = document.createElement("div");
  host.innerHTML = renderToStaticMarkup(<ActiveNotesCard plan={notesPlan([
    { category: "injury", text: "No contact training until cleared." },
    { category: "conditioning", text: "Aerobic base is built on easy bike work." },
  ])} />);
  const restriction = Array.from(host.querySelectorAll(".sp-note-text")).find(node => node.textContent === "No contact training until cleared.");
  assert.ok(restriction); assert.equal(restriction.closest("details"), null);
  assert.ok(host.querySelector("details"));
});

test("Plan notes: restriction-only plans show a static heading, no empty disclosure", () => {
  const host = document.createElement("div");
  host.innerHTML = renderToStaticMarkup(<ActiveNotesCard plan={notesPlan([
    { category: "injury", text: "No contact training until cleared." },
    { category: "weight_cut", text: "Stay within 5% of fight weight." },
  ])} />);
  assert.equal(host.querySelector("details"), null);
  assert.equal(host.querySelector(".sp-collapse-action"), null);
  assert.match(host.querySelector("h3")?.textContent ?? "", /Plan notes/);
  assert.equal(host.querySelectorAll(".sp-note").length, 2);
});

test("the Plan page opens on the calendar; other hosts keep the list", () => {
  const calendar = renderToStaticMarkup(<StructuredPlanRenderer plan={trainingPlan} defaultView="calendar" today={new Date(2026, 9, 28, 12)} />);
  assert.match(calendar, /class="sp-card cm-calendar"/);
  assert.doesNotMatch(calendar, /class="sp-weeks cm-days"/);
  const list = renderToStaticMarkup(<StructuredPlanRenderer plan={trainingPlan} today={new Date(2026, 9, 28, 12)} />);
  assert.match(list, /class="sp-weeks cm-days"/);
});
