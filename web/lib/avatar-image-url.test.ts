import test from "node:test";
import assert from "node:assert/strict";

import { isSafeAvatarImageUrl } from "./avatar-image-url";

test("avatar image URLs allow HTTPS and safe data images", () => {
  assert.equal(isSafeAvatarImageUrl("https://example.com/photo.jpg"), true);
  assert.equal(isSafeAvatarImageUrl("  https://example.com/photo.jpg  "), true);
  assert.equal(isSafeAvatarImageUrl("data:image/png;base64,iVBORw0KGgo="), true);
  assert.equal(isSafeAvatarImageUrl("  data:image/png;base64,iVBORw0KGgo=  "), true);
});

test("avatar image URLs reject HTTP, malformed data images, and invalid values", () => {
  assert.equal(isSafeAvatarImageUrl("http://example.com/photo.jpg"), false);
  assert.equal(isSafeAvatarImageUrl("data:image/png;base64,not valid"), false);
  assert.equal(isSafeAvatarImageUrl(null), false);
  assert.equal(isSafeAvatarImageUrl(undefined), false);
  assert.equal(isSafeAvatarImageUrl(""), false);
});

test("avatar image URLs reject scriptable formats and embedded credentials", () => {
  assert.equal(isSafeAvatarImageUrl("data:image/svg+xml;base64,PHN2Zz4="), false);
  assert.equal(isSafeAvatarImageUrl("data:text/html;base64,PHNjcmlwdD4="), false);
  assert.equal(isSafeAvatarImageUrl("javascript:alert(1)"), false);
  assert.equal(isSafeAvatarImageUrl("https://user:pass@example.com/photo.jpg"), false);
});
