import test from "node:test";
import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";

import { SafetyNote } from "./safety-note";
import { SAFETY_RED_FLAGS, SAFETY_RED_FLAG_HEADING } from "@/lib/safety-copy";

test("SafetyNote renders its disclaimer body", () => {
  const html = renderToStaticMarkup(<SafetyNote>Unlxck is not medical advice.</SafetyNote>);
  assert.ok(html.includes("Unlxck is not medical advice."));
  assert.ok(html.includes("safety-note"));
});

test("SafetyNote omits the red-flag list unless asked", () => {
  const html = renderToStaticMarkup(<SafetyNote>Body only.</SafetyNote>);
  assert.ok(!html.includes(SAFETY_RED_FLAG_HEADING));
});

test("SafetyNote shows the expandable red-flag checklist when enabled", () => {
  const html = renderToStaticMarkup(<SafetyNote showRedFlags>Body.</SafetyNote>);
  assert.ok(html.includes(SAFETY_RED_FLAG_HEADING));
  for (const flag of SAFETY_RED_FLAGS) {
    assert.ok(html.includes(flag), `expected red flag rendered: ${flag}`);
  }
});

test("warning tone is reflected in the class name", () => {
  const html = renderToStaticMarkup(<SafetyNote tone="warning">Warn.</SafetyNote>);
  assert.ok(html.includes("safety-note-warning"));
});
