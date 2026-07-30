import test from "node:test";
import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";

import { OnboardingTrustNote } from "./onboarding-trust-note";
import { TRUST_INTRO_HEADING, TRUST_POINTS } from "@/lib/trust-copy";

test("the note renders the heading and every trust point", () => {
  const html = renderToStaticMarkup(<OnboardingTrustNote />);
  assert.ok(html.includes(TRUST_INTRO_HEADING));
  for (const point of TRUST_POINTS) {
    assert.ok(html.includes(point.title), `expected trust point rendered: ${point.title}`);
  }
});

test("the copy never anthropomorphises the system", () => {
  const html = renderToStaticMarkup(<OnboardingTrustNote />).toLowerCase();
  for (const phrase of ["the ai", "our ai", "ai thinks", "ai decides", "the algorithm"]) {
    assert.ok(!html.includes(phrase), `trust copy must not anthropomorphise: ${phrase}`);
  }
});

test("the copy makes no medical or safety claim", () => {
  // Medical wording is owned by safety-copy.ts and rendered by SafetyNote. This
  // note explains how decisions are made and must not drift into clearance
  // language, which would read as a claim the product cannot make.
  const html = renderToStaticMarkup(<OnboardingTrustNote />).toLowerCase();
  for (const phrase of ["safe to train", "medical", "diagnos", "cleared to"]) {
    assert.ok(!html.includes(phrase), `trust copy must not make a safety claim: ${phrase}`);
  }
});
