import assert from "node:assert/strict";
import test from "node:test";
import { renderToStaticMarkup } from "react-dom/server";

import { PublicGenerationScreen } from "./public-generation-screen";

test("public build omits diagnostics and shows leave reassurance", () => {
  const html = renderToStaticMarkup(<PublicGenerationScreen phase="running" milestones={[{ code: "designing_camp", label: "Designing your camp", detail: "", at: "" }]} />);
  assert.match(html, /YOUR CAMP IS TAKING SHAPE/);
  assert.match(html, /Safe to leave/);
  for (const privateCopy of ["Job state", "payload", "Stage 1", "model", "Plan activity", "Elapsed"]) assert.ok(!html.includes(privateCopy));
});

test("public failure gives recovery actions without rendering raw errors", () => {
  const html = renderToStaticMarkup(<PublicGenerationScreen phase="failed" error="worker traceback: secret" failureKind="job_failed" canRetry onRetry={() => {}} onReturnToWorkspace={() => {}} />);
  assert.match(html, /Try again/);
  assert.match(html, /Return to workspace/);
  assert.ok(!html.includes("traceback"));
});
