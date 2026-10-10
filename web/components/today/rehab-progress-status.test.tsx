import test from "node:test";
import assert from "node:assert/strict";
import { window as domWindow } from "../test-dom";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { renderToStaticMarkup } from "react-dom/server";
import { RehabProgressStatus } from "./rehab-progress-status";
import type { InjuryFlagRecord } from "@/lib/types";

const decision: NonNullable<InjuryFlagRecord["rehab_decision"]> = {
  outcome: "prescribed_rehab", summary: "Reviewed rehab", reason_codes: [], stage: "restore",
  progression: { next_transition: { to_stage: "load", status: "blocked", target_stage_live: true,
    reason_codes: ["rehabilitation_loading_not_reported"], requirements: [
      { requirement_id: "history", kind: "complete_history", status: "pass", reason_code: "history_complete" },
      { requirement_id: "permission", kind: "functional_checkpoint", status: "unknown", reason_code: "rehabilitation_loading_not_reported" },
    ] } },
};

test("progression is one compact row, only when the engine supplies a stage", () => {
  assert.equal(renderToStaticMarkup(<RehabProgressStatus decision={{ ...decision, stage: undefined }} />), "");
  const html = renderToStaticMarkup(<RehabProgressStatus decision={decision} statusLine="Done for today · next Sat 10 Oct" />);
  assert.match(html, /<button[^>]*class="injury-progress"/);
  assert.match(html, /Progression to Load/);
  assert.match(html, /Done for today · next Sat 10 Oct/);
  // The summary row above already shows the stage and its meter.
  assert.doesNotMatch(html, /aria-current="step"|data-complete|Rehab stage<|\d+%/);
});

test("a closed next stage says so, and a stage with no next stage and no status renders nothing", () => {
  const closed = renderToStaticMarkup(<RehabProgressStatus decision={{ ...decision, progression: { next_transition: {
    ...decision.progression!.next_transition!, status: "closed", target_stage_live: false } } }} />);
  assert.match(closed, /Progression to Load · Closed/);
  assert.equal(renderToStaticMarkup(<RehabProgressStatus decision={{ ...decision, progression: {} }} />), "");
});

for (const closed of [false, true]) {
  test(`progression details preserve engine holds and closed=${closed}`, async () => {
    const container = document.createElement("div"); document.body.appendChild(container);
    const root = createRoot(container);
    const current = closed ? { ...decision, stage: "load" as const, progression: { next_transition: {
      ...decision.progression!.next_transition!, to_stage: "dynamic", status: "closed", target_stage_live: false,
    } } } : decision;
    try {
      await act(async () => root.render(<RehabProgressStatus decision={current} />));
      const trigger = container.querySelector("button")!;
      trigger.focus();
      await act(async () => trigger.click());
      const dialog = document.querySelector<HTMLElement>('[role="dialog"]')!;
      assert.ok(dialog);
      assert.equal(document.body.style.position, "fixed");
      if (closed) {
        assert.match(dialog.textContent ?? "", /next stage is closed/);
        assert.equal(dialog.querySelector(".injury-requirements"), null);
      } else {
        assert.match(dialog.textContent ?? "", /Complete rehab historyComplete/);
        assert.match(dialog.textContent ?? "", /Not yet confirmed/);
        assert.match(dialog.textContent ?? "", /Report what your clinician has permitted/);
        assert.doesNotMatch(dialog.textContent ?? "", /medical clearance issued|heel-rise|assessor/);
      }
      await act(async () => document.dispatchEvent(new domWindow.KeyboardEvent("keydown", { key: "Escape", bubbles: true })));
      assert.equal(document.querySelector('[role="dialog"]'), null);
      assert.equal(document.activeElement, trigger);
      assert.equal(document.body.style.position, "");
    } finally { act(() => root.unmount()); container.remove(); }
  });
}


test("missing rehab responses direct athletes to rehab records, not the daily check-in", async () => {
  const container = document.createElement("div"); document.body.appendChild(container);
  const root = createRoot(container);
  try {
    await act(async () => root.render(<RehabProgressStatus decision={{ ...decision, progression: { next_transition: {
      ...decision.progression!.next_transition!, reason_codes: ["during_response_not_reported", "next_day_response_not_reported"], requirements: [],
    } } }} />));
    await act(async () => container.querySelector("button")!.click());
    const text = document.querySelector('[role="dialog"]')!.textContent ?? "";
    assert.match(text, /Log your rehab session and answer its injury-response question/);
    assert.match(text, /next-day rehab follow-up when it appears in Today/);
    assert.doesNotMatch(text, /Better, Same or Worse/);
  } finally { act(() => root.unmount()); container.remove(); }
});

test("missing elbow suitability shows the actual blocker once without another questionnaire", async () => {
  const container = document.createElement("div"); document.body.appendChild(container);
  const root = createRoot(container);
  try {
    await act(async () => root.render(<RehabProgressStatus decision={{ ...decision, policy_id: "elbow_tendonitis",
      progression: { next_transition: { ...decision.progression!.next_transition!,
        reason_codes: ["assessment_observation_missing", "elbow_function_assessment_incomplete"], requirements: [
          { requirement_id: "function", kind: "functional_checkpoint", status: "unknown", reason_code: "assessment_observation_missing" },
          { requirement_id: "observations", kind: "input_availability", status: "unknown", reason_code: "elbow_function_assessment_incomplete" },
        ] } } }} />));
    await act(async () => container.querySelector("button")!.click());
    const dialog = document.querySelector('[role="dialog"]')!;
    const text = dialog.textContent ?? "";
    assert.equal(dialog.querySelectorAll(".injury-requirements li").length, 1);
    assert.match(text, /LOAD is on hold/);
    assert.match(text, /Clearance and completed rehab cannot confirm grip, movement and tolerance/);
    assert.doesNotMatch(text, /Report your clinician|Leave unassessed|timestamp|date|questionnaire|rehab engine/i);
    assert.equal(dialog.querySelectorAll("form, input, select, textarea").length, 0);
  } finally { act(() => root.unmount()); container.remove(); }
});
