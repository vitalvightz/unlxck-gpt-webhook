import assert from "node:assert/strict";
import test from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { StepValidationPanel } from "./onboarding-step-validation";

test("compact checklist counts pending and warning items without losing safety context", () => {
  const html = renderToStaticMarkup(<StepValidationPanel stepLabel="Restrictions" title="Review restrictions"
    description="Check the highlighted answers." checks={[
      { label: "Area selected", status: "done" },
      { label: "Answer impact", status: "pending" },
      { label: "Review head-impact symptoms", status: "warning" },
    ]} />);
  assert.match(html, /<summary[^>]*>.*Restrictions check.*2 left/);
  assert.doesNotMatch(html, /<details[^>]* open/);
  assert.match(html, /data-status="warning">Review head-impact symptoms/);
  assert.match(html, /Check the highlighted answers/);
});

test("complete checklist shows ready and retains details behind its disclosure", () => {
  const html = renderToStaticMarkup(<StepValidationPanel stepLabel="Restrictions" title="Ready to continue"
    description="Details saved." checks={[{ label: "No restrictions", status: "done" }]} />);
  assert.match(html, /Ready/);
  assert.match(html, /data-status="done">No restrictions/);
  assert.doesNotMatch(html, /left|<details[^>]* open/);
});
