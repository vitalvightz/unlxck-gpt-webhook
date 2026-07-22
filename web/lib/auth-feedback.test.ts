import assert from "node:assert/strict";
import test from "node:test";

import { AUTH_FEEDBACK, getLoginErrorMessage, getMagicLinkErrorMessage } from "./auth-feedback.ts";

test("maps invalid credentials without exposing the provider message", () => {
  assert.equal(
    getLoginErrorMessage({
      code: "invalid_credentials",
      message: "Invalid login credentials from provider",
      status: 400,
    }),
    AUTH_FEEDBACK.incorrectCredentials,
  );
});

test("recognizes legacy invalid credential responses without an error code", () => {
  assert.equal(
    getLoginErrorMessage({ message: "Invalid login credentials", status: 400 }),
    AUTH_FEEDBACK.incorrectCredentials,
  );
});

test("maps request and email rate limits to one controlled message", () => {
  assert.equal(
    getLoginErrorMessage({ code: "over_request_rate_limit", status: 400 }),
    AUTH_FEEDBACK.tooManyAttempts,
  );
  assert.equal(
    getMagicLinkErrorMessage({ code: "over_email_send_rate_limit", status: 400 }),
    AUTH_FEEDBACK.tooManyAttempts,
  );
  assert.equal(getLoginErrorMessage({ status: 429 }), AUTH_FEEDBACK.tooManyAttempts);
});

test("maps Supabase retryable fetch failures to the connection message", () => {
  assert.equal(
    getLoginErrorMessage({ name: "AuthRetryableFetchError", message: "Failed to fetch", status: 0 }),
    AUTH_FEEDBACK.connectionFailure,
  );
  assert.equal(
    getMagicLinkErrorMessage({ name: "AuthRetryableFetchError", message: "Failed to fetch", status: 503 }),
    AUTH_FEEDBACK.connectionFailure,
  );
  assert.equal(getLoginErrorMessage({ code: "request_timeout" }), AUTH_FEEDBACK.connectionFailure);
});

test("uses controlled fallbacks for unknown provider errors", () => {
  assert.equal(
    getLoginErrorMessage({ code: "unexpected_failure", message: "Internal provider detail" }),
    AUTH_FEEDBACK.signInFailure,
  );
  assert.equal(
    getMagicLinkErrorMessage({ code: "unexpected_failure", message: "Internal provider detail" }),
    AUTH_FEEDBACK.magicLinkFailure,
  );
});
