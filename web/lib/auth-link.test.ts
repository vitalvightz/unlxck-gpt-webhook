import assert from "node:assert/strict";
import test from "node:test";

import { AUTH_LINK_FEEDBACK, readAuthLinkParams, readAuthLinkStatus } from "./auth-link.ts";

test("reads an expired implicit-flow link from the URL fragment", () => {
  const status = readAuthLinkStatus({
    hash: "#error=access_denied&error_code=otp_expired&error_description=Email+link+is+invalid+or+has+expired",
    search: "",
  });
  assert.equal(status.kind, "error");
  assert.equal(status.kind === "error" && status.code, "otp_expired");
  assert.equal(status.kind === "error" && status.message, AUTH_LINK_FEEDBACK.expired);
});

test("reads an expired link from the query string", () => {
  const status = readAuthLinkStatus({
    hash: "",
    search: "?error=access_denied&error_code=otp_expired",
  });
  assert.equal(status.kind, "error");
  assert.equal(status.kind === "error" && status.message, AUTH_LINK_FEEDBACK.expired);
});

test("treats an unknown error code as an invalid link", () => {
  const status = readAuthLinkStatus({ hash: "", search: "?error=server_error" });
  assert.equal(status.kind, "error");
  assert.equal(status.kind === "error" && status.message, AUTH_LINK_FEEDBACK.invalid);
});

test("falls back to the description when Supabase omits a machine-readable code", () => {
  const status = readAuthLinkStatus({
    hash: "#error=access_denied&error_description=Email+link+is+invalid+or+has+expired",
    search: "",
  });
  assert.equal(status.kind === "error" && status.message, AUTH_LINK_FEEDBACK.expired);
});

test("never surfaces the raw provider description", () => {
  const status = readAuthLinkStatus({
    hash: "#error=access_denied&error_description=Contact+evil.example+for+support",
    search: "",
  });
  assert.equal(status.kind === "error" && status.message, AUTH_LINK_FEEDBACK.invalid);
});

test("detects implicit-flow credentials and the recovery type", () => {
  const status = readAuthLinkStatus({
    hash: "#access_token=abc&refresh_token=def&expires_in=3600&type=recovery",
    search: "",
  });
  assert.equal(status.kind, "credentials");
  assert.equal(status.kind === "credentials" && status.type, "recovery");
});

test("detects PKCE credentials on the query string", () => {
  const status = readAuthLinkStatus({ hash: "", search: "?code=abc123" });
  assert.equal(status.kind, "credentials");
});

test("reports a plain page visit as none", () => {
  assert.equal(readAuthLinkStatus({ hash: "", search: "?next=/today" }).kind, "none");
  assert.equal(readAuthLinkStatus({ hash: "#", search: "" }).kind, "none");
});

test("lets the fragment win over the query string", () => {
  const params = readAuthLinkParams({ hash: "#type=recovery", search: "?type=magiclink" });
  assert.equal(params.get("type"), "recovery");
});
