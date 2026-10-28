import test from "node:test";
import assert from "node:assert/strict";

import { hasSignupAccess, isValidAccessCode, normalizeAccessCode, signupAccessToken } from "./signup-access";

test("the launch code unlocks signup, tolerating spaces", () => {
  assert.equal(isValidAccessCode("63839"), true);
  assert.equal(isValidAccessCode(" 63 839 "), true);
});

test("wrong, partial or empty codes do not unlock", () => {
  for (const code of ["", "6383", "638390", "12345", "63838"]) assert.equal(isValidAccessCode(code), false, code);
});

test("SIGNUP_ACCESS_CODE overrides the launch code and retires old cookies", () => {
  const before = signupAccessToken();
  process.env.SIGNUP_ACCESS_CODE = "new-2027";
  try {
    assert.equal(isValidAccessCode("63839"), false);
    assert.equal(isValidAccessCode("NEW2027"), true);
    assert.equal(hasSignupAccess(before), false, "a cookie for the old code no longer unlocks");
    assert.equal(hasSignupAccess(signupAccessToken()), true);
  } finally {
    delete process.env.SIGNUP_ACCESS_CODE;
  }
});

test("the cookie never holds the code itself", () => {
  assert.ok(!signupAccessToken().includes("63839"));
  assert.equal(hasSignupAccess(undefined), false);
  assert.equal(normalizeAccessCode("ab-12"), "AB12");
});
