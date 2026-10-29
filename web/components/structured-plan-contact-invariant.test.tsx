import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { renderToStaticMarkup } from "react-dom/server";

import { CampDayCard } from "./structured-plan-renderer";
import { dayCompletion } from "@/lib/camp-map";
import { contactTimerTarget } from "@/lib/session-timer/contact";
import { getPhysicalSessions, isCoachLedPhysicalTrainingDay } from "@/lib/structured-plan";
import type { StructuredDay } from "@/lib/types";

// The four production Saturdays (anonymised) exactly as they were saved:
// D-42/D-28 carry coach_led_contact, D-35/D-21 had it null beside Self-Review.
const fixture = path.resolve(process.cwd(), "../tests/fixtures/sparring_contact/production_contact_days.json");
const saved: StructuredDay[] = JSON.parse(readFileSync(fixture, "utf8"));
const byLabel = new Map(saved.map((day) => [String(day.countdown_label), day]));

/** The card as the server now serves it: contact surfaced, nothing else changed. */
function served(label: string): StructuredDay {
  const day = structuredClone(byLabel.get(label)!);
  day.today_card = { ...day.today_card!, coach_led_contact: "Hard sparring" };
  return day;
}

test("the saved production D-35/D-21 cards are what hid the sparring", () => {
  for (const label of ["D-35", "D-21"]) {
    const day = byLabel.get(label)!;
    assert.equal(day.today_card?.coach_led_contact, null);
    const html = renderToStaticMarkup(<CampDayCard day={day} />);
    assert.match(html, /cm-day-support[^>]*>Zero load/, label);
    assert.equal(contactTimerTarget(day), null, label);
    assert.equal(isCoachLedPhysicalTrainingDay(day), false, label);
  }
});

for (const label of ["D-42", "D-35", "D-28", "D-21"]) {
  test(`${label} renders hard sparring beside its zero-load session, never zero load`, () => {
    const day = label === "D-42" || label === "D-28" ? byLabel.get(label)! : served(label);
    const html = renderToStaticMarkup(<CampDayCard day={day} defaultOpen />);

    assert.match(html, /cm-day-context-contact/);
    assert.match(html, /Hard sparring/);
    assert.doesNotMatch(html, /cm-day-support[^>]*>Zero load/);
    // The zero-load companion still renders as its own card, unchanged.
    const companion = label === "D-35" || label === "D-21" ? "Self-Review Cues" : "Breathing Reset";
    assert.match(html, new RegExp(companion));
    assert.match(html, /0 of 1 complete/);

    // Classification, completion summary and the contact round timer agree.
    assert.equal(getPhysicalSessions(day).length, 0);
    assert.equal(isCoachLedPhysicalTrainingDay(day), true);
    assert.deepEqual(dayCompletion(day), { done: 0, total: 1 });
    assert.deepEqual(contactTimerTarget(day), { kind: "sparring", headline: "Hard sparring" });
    // Completion/logging identity of the companion session is unchanged.
    assert.equal(day.sessions?.[0]?.session_id, byLabel.get(label)!.sessions?.[0]?.session_id);
  });
}
