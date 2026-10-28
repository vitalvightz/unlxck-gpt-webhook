import test from "node:test";
import assert from "node:assert/strict";

import { scrambleText } from "./unlock-glitch-text";

test("scrambleText resolves left to right as progress grows", () => {
  const fixed = () => 0;
  assert.equal(scrambleText("UNLXCK", 0, fixed), "######");
  assert.equal(scrambleText("UNLXCK", 0.5, fixed), "UNL###");
  assert.equal(scrambleText("UNLXCK", 1, fixed), "UNLXCK");
});

test("scrambleText keeps spaces and length so the line never reflows", () => {
  const out = scrambleText("Your potential", 0.2);
  assert.equal(out.length, "Your potential".length);
  assert.equal(out[4], " ");
});

test("scrambleText clamps progress outside 0..1", () => {
  assert.equal(scrambleText("ab", -1, () => 0), "##");
  assert.equal(scrambleText("ab", 2), "ab");
});

test("the server render is the fixed placeholder, so hydration always matches", async () => {
  const { createElement } = await import("react");
  const { renderToString } = await import("react-dom/server");
  const { UnlockGlitchText } = await import("./unlock-glitch-text");
  const html = renderToString(createElement(UnlockGlitchText, { text: "UNLXCK" }));
  assert.match(html, /data-state="locked"/);
  assert.match(html, />######</);
});
