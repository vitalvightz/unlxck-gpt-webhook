import test from "node:test";
import assert from "node:assert/strict";

import {
  contactRoundsItem,
  contactTimerTarget,
  freeRoundsItem,
  parseRoundsFromText,
} from "./contact.ts";
import type { StructuredDay } from "../types.ts";

test("a session-less declared sparring day is a hard sparring target", () => {
  const day: StructuredDay = {
    date: "2026-09-25",
    day_type: "high",
    today_card: { headline: "Hard sparring (coach-led)" },
    sessions: [],
  } as StructuredDay;
  assert.deepEqual(contactTimerTarget(day), { kind: "sparring", headline: "Hard sparring (coach-led)" });
});

test("coach-led contact beside an app session is still a target", () => {
  const day = {
    date: "2026-09-25",
    today_card: { headline: "Mobility flush", coach_led_contact: "Light combat — coach-led" },
    sessions: [{ session_id: "s1", title: "Mobility flush", blocks: [] }],
  } as StructuredDay;
  assert.equal(contactTimerTarget(day)?.kind, "light_combat");
});

test("rest days and ordinary app-session days have no contact target", () => {
  assert.equal(
    contactTimerTarget({ day_type: "rest", today_card: { headline: "Full rest and mobility" }, sessions: [] } as StructuredDay),
    null,
  );
  assert.equal(
    contactTimerTarget({
      today_card: { headline: "Strength" },
      sessions: [{ session_id: "s1", title: "Strength", blocks: [] }],
    } as StructuredDay),
    null,
  );
  assert.equal(contactTimerTarget(null), null);
});

test("round structure is read from the contact line when stated", () => {
  assert.deepEqual(parseRoundsFromText("Hard sparring 6 x 3 min, 1 min rest"), {
    rounds: 6,
    workSec: 180,
    restSec: 60,
  });
  assert.deepEqual(parseRoundsFromText("5 rounds of 5 min"), { rounds: 5, workSec: 300, restSec: null });
  assert.deepEqual(parseRoundsFromText("Sparring — 4 rounds"), { rounds: 4, workSec: null, restSec: null });
  assert.deepEqual(parseRoundsFromText("Hard sparring (coach-led)"), {
    rounds: null,
    workSec: null,
    restSec: null,
  });
});

test("contact rounds offer presets and ask for setup unless the plan states the round length", () => {
  const unstated = contactRoundsItem({ kind: "sparring", headline: "Hard sparring (coach-led)" });
  assert.equal(unstated.title, "Hard sparring");
  assert.equal(unstated.sparring, true);
  assert.equal(unstated.presets, true);
  assert.equal(unstated.needsSetup, true);

  const stated = contactRoundsItem({ kind: "light_combat", headline: "Light sparring 4 x 2 min" });
  assert.equal(stated.title, "Light sparring");
  assert.equal(stated.rounds, 4);
  assert.equal(stated.workSec, 120);
  assert.equal(stated.needsSetup, false);
});

test("the plain round timer starts on boxing rounds with presets", () => {
  const item = freeRoundsItem();
  assert.equal(item.workSec, 180);
  assert.equal(item.restSec, 60);
  assert.equal(item.presets, true);
  assert.equal(item.needsSetup, false);
});
