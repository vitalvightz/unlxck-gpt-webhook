import assert from "node:assert/strict";
import test from "node:test";

import {
  getAvailabilityConsistency,
  getHardSparringWarning,
  getSparringConsistency,
} from "./training-schedule.ts";

test("flags sessions above the available training days", () => {
  assert.deepStrictEqual(
    getAvailabilityConsistency(["Monday", "Wednesday"], 3),
    {
      hardError: "You selected 2 available days but planned 3 weekly sessions.",
      softWarning: null,
    },
  );
});

test("flags hard sparring days that sit outside the available schedule", () => {
  assert.deepStrictEqual(
    getSparringConsistency(["Monday", "Wednesday"], ["Friday"], []),
    {
      hardError: "Hard sparring days must also be selected as available days: Friday.",
      softWarning: null,
    },
  );
});

test("flags overlap between hard sparring and technical skill days", () => {
  assert.deepStrictEqual(
    getSparringConsistency(["Monday", "Wednesday", "Friday"], ["Wednesday"], ["Wednesday", "Friday"]),
    {
      hardError: "A day cannot be both hard sparring and technical / lighter skill: Wednesday.",
      softWarning: null,
    },
  );
});

test("does not warn when hard sparring stays at two days or fewer", () => {
  assert.deepStrictEqual(
    getHardSparringWarning(["Monday", "Wednesday"], 5),
    {
      acknowledgementContextKey: "hard-sparring:5:Monday|Wednesday",
      message: null,
      requiresAcknowledgement: false,
    },
  );
});

test("warns when hard sparring reaches three or more days", () => {
  assert.deepStrictEqual(
    getHardSparringWarning(["Monday", "Wednesday", "Friday"], 5),
    {
      acknowledgementContextKey: "hard-sparring:5:Friday|Monday|Wednesday",
      message:
        "You selected 3 hard sparring days inside 5 planned weekly sessions. That's a high contact load, so confirm the athlete can recover from it before continuing.",
      requiresAcknowledgement: true,
    },
  );
});

test("changes the acknowledgement reset key when hard days or session count change", () => {
  const baseline = getHardSparringWarning(["Monday", "Wednesday", "Friday"], 5).acknowledgementContextKey;

  assert.notEqual(
    baseline,
    getHardSparringWarning(["Monday", "Thursday", "Friday"], 5).acknowledgementContextKey,
  );

  assert.notEqual(
    baseline,
    getHardSparringWarning(["Monday", "Wednesday", "Friday"], 4).acknowledgementContextKey,
  );
});
