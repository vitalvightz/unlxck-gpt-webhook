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

test("stage is only shown when supplied by the engine", () => {
  assert.equal(renderToStaticMarkup(<RehabProgressStatus decision={{ ...decision, stage: undefined }} />), "");
  const html = renderToStaticMarkup(<RehabProgressStatus decision={decision} />);
  assert.match(html, /Restore/);
  assert.match(html, /Next: Load/);
  assert.equal((html.match(/aria-current="step"/g) ?? []).length, 1);
  assert.equal((html.match(/data-complete="true"/g) ?? []).length, 2);
  assert.doesNotMatch(html, /\d+%/);
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
