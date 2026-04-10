import assert from "node:assert/strict";
import test from "node:test";

const {
  getAvailabilityConsistency,
  getHardSparringLoadWarning,
  getHardSparringWarningContextKey,
  getSparringConsistency,
} = await import(new URL("./training-schedule.ts", import.meta.url).href);

test("availability consistency blocks weekly sessions above available days", () => {
  const result = getAvailabilityConsistency(["Monday", "Wednesday"], 3);

  assert.equal(
    result.hardError,
    "You selected 2 days available but planned 3 weekly sessions.",
  );
  assert.equal(result.softWarning, null);
});

test("sparring consistency rejects hard or technical days outside availability", () => {
  const hardResult = getSparringConsistency(["Monday", "Wednesday"], ["Monday", "Friday"], []);
  const technicalResult = getSparringConsistency(["Monday", "Wednesday"], [], ["Tuesday"]);

  assert.equal(
    hardResult.hardError,
    "Hard sparring days must also be selected as available days: Friday.",
  );
  assert.equal(
    technicalResult.hardError,
    "Technical / lighter skill days must also be selected as available days: Tuesday.",
  );
});

test("hard sparring warning stays off below three hard days", () => {
  const result = getHardSparringLoadWarning(["Monday", "Thursday"], 4);

  assert.equal(result.requiresConfirmation, false);
  assert.equal(result.warning, null);
});

test("hard sparring warning requires confirmation at three days and mentions weekly sessions", () => {
  const result = getHardSparringLoadWarning(["Monday", "Wednesday", "Friday"], 4);

  assert.equal(result.requiresConfirmation, true);
  assert.match(result.warning ?? "", /3 hard sparring days inside 4 planned weekly sessions/i);
  assert.match(result.warning ?? "", /only one planned session not marked as hard sparring/i);
});

test("hard sparring warning gets stronger when hard days exceed total weekly sessions", () => {
  const result = getHardSparringLoadWarning(["Monday", "Wednesday", "Friday"], 2);

  assert.equal(result.requiresConfirmation, true);
  assert.match(result.warning ?? "", /more hard sparring days than total planned sessions/i);
});

test("hard sparring warning context key changes when selected days or sessions change", () => {
  const original = getHardSparringWarningContextKey(["Wednesday", "Monday", "Friday"], 4);
  const differentDays = getHardSparringWarningContextKey(["Monday", "Wednesday", "Saturday"], 4);
  const differentSessions = getHardSparringWarningContextKey(["Monday", "Wednesday", "Friday"], 5);

  assert.equal(original, "Friday|Monday|Wednesday::4");
  assert.notEqual(original, differentDays);
  assert.notEqual(original, differentSessions);
});
