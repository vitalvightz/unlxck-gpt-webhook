import assert from "node:assert/strict";
import test from "node:test";

import { hasInternalPreviousPage } from "./internal-back.ts";

const app = "https://app.unlxck.com";

test("a client-side visit to Create steps back inside the app", () => {
  assert.equal(hasInternalPreviousPage({ documentUrl: `${app}/plans`, currentUrl: `${app}/create`, referrer: "https://google.com/" }), true);
});

test("Create opened directly from another site or a new tab falls back to Home", () => {
  assert.equal(hasInternalPreviousPage({ documentUrl: `${app}/create`, currentUrl: `${app}/create`, referrer: "https://google.com/" }), false);
  assert.equal(hasInternalPreviousPage({ documentUrl: `${app}/create`, currentUrl: `${app}/create`, referrer: "" }), false);
  assert.equal(hasInternalPreviousPage({ documentUrl: undefined, currentUrl: `${app}/create`, referrer: "" }), false);
});

test("a full page load from an UNLXCK page still steps back", () => {
  assert.equal(hasInternalPreviousPage({ documentUrl: `${app}/create`, currentUrl: `${app}/create`, referrer: `${app}/today` }), true);
});
