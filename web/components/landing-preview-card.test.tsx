import assert from "node:assert/strict";
import test from "node:test";
import { NextIntlClientProvider } from "next-intl";
import { renderToString } from "react-dom/server";
import messages from "../messages/en.json";
import { LandingPreviewCard } from "./landing-preview-card";

// React separates adjacent text with <!-- --> markers; drop them to match text.
const render = () =>
  renderToString(
    <NextIntlClientProvider locale="en" timeZone="Europe/London" messages={messages}>
      <LandingPreviewCard />
    </NextIntlClientProvider>,
  ).replaceAll("<!-- -->", "");

test("the preview card first renders the session as planned", () => {
  const html = render();
  assert.match(html, /data-phase="planned"/);
  assert.match(html, /5 × 3/, "heavy bag starts at its planned dose");
  assert.ok(!html.includes("data-change"), "no row is marked changed before the adjustment plays");
});

test("the adjusted content is all in the markup, ready to reveal", () => {
  const html = render();
  for (const text of ["Modify today", "Reaction drills", "Reduced", "Added", "Unchanged"]) {
    assert.ok(html.includes(text), `${text} is rendered`);
  }
});
