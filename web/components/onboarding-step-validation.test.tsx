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
  assert.match(html, /<summary[^>]*>.*Restrictions checklist.*2 to do/);
  assert.doesNotMatch(html, /<details[^>]* open/);
  assert.match(html, /data-status="warning">Review head-impact symptoms/);
  assert.match(html, /Check the highlighted answers/);
});

test("complete checklist shows ready and retains details behind its disclosure", () => {
  const html = renderToStaticMarkup(<StepValidationPanel stepLabel="Restrictions" title="Ready to continue"
    description="Details saved." checks={[{ label: "No restrictions", status: "done" }]} defaultOpen />);
  assert.match(html, /Ready/);
  assert.match(html, /data-status="done">No restrictions/);
  assert.doesNotMatch(html, /to do|<details[^>]* open/);
});

test("unresolved checks with a field target offer a Fix button; resolved ones do not", () => {
  const html = renderToStaticMarkup(<StepValidationPanel stepLabel="Review" title="Ready to build"
    description="Fix anything still open." onFix={() => {}} defaultOpen checks={[
      { label: "Combat sport picked.", status: "done", fix: { fieldId: "technicalStyle", step: 0 } },
      { label: "Add your fight date.", status: "pending", fix: { fieldId: "fightDate", step: 1 } },
      { label: "No target here.", status: "warning" },
    ]} />);
  assert.match(html, /<details[^>]* open/);
  assert.equal(html.match(/>Fix<\/button>/g)?.length, 1);
  assert.match(html, /Add your fight date\. <button[^>]*>Fix<\/button>/);
});
