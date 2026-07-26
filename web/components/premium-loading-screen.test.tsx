import test from "node:test";
import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";

import { PremiumLoadingScreen } from "./premium-loading-screen";

const noop = () => {};

function renderFailure(props: Partial<Parameters<typeof PremiumLoadingScreen>[0]> = {}) {
  return renderToStaticMarkup(
    <PremiumLoadingScreen
      phase="failed"
      error="Plan generation failed unexpectedly."
      onRetry={noop}
      canRetry
      onOpenPlanHistory={noop}
      onReturnToWorkspace={noop}
      onRefineIntake={noop}
      {...props}
    />,
  );
}

test("a failed build offers no status refresh", () => {
  // Re-reading a finished job cannot revive it; a live-looking status control
  // on a dead build made the screen read as if it were generating again.
  const html = renderFailure({ failureKind: "job_failed" });
  assert.ok(!html.includes("Refresh status"));
  assert.ok(!html.includes("Update status"));
});

test("a retryable failure still offers a way out of the screen", () => {
  const html = renderFailure({ failureKind: "job_failed" });
  assert.ok(html.includes("Try again"));
  assert.ok(html.includes("Return to workspace"));
});

test("a failure that cannot be retried does not offer a retry", () => {
  const html = renderFailure({ failureKind: "invalid_intake", canRetry: false, error: "Pick more training days." });
  assert.ok(!html.includes("Try again"));
  assert.ok(html.includes("Fix my intake"));
  assert.ok(html.includes("Return to workspace"));
});

test("a failed build drops the live progress rail", () => {
  // The rail would tick four stages "complete" and blame the last one.
  const html = renderFailure({ failureKind: "stalled", canRetry: true });
  assert.ok(!html.includes("Generation workflow"));
  assert.ok(html.includes("What happened"));
});

test("a live build keeps the progress rail", () => {
  const html = renderToStaticMarkup(
    <PremiumLoadingScreen phase="running" startedAtMs={Date.now()} />,
  );
  assert.ok(html.includes("Generation workflow"));
});

test("engineering error text is not shown to the athlete", () => {
  const html = renderFailure({
    failureKind: "job_failed",
    error: "Stage 2 first_pass prompt too large: 214880 chars",
  });
  assert.ok(!html.includes("first_pass"));
  assert.ok(html.includes("too large to finalize in one pass"));
});
