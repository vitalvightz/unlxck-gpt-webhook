import assert from "node:assert/strict";
import test from "node:test";

import "../components/test-dom";
import { INSTALL_PROMPT_EVENT, offerInstallPrompt, offerPushNotifications, PUSH_PROMPT_EVENT } from "./push-prompt";

test("a ready plan offers install first and holds notifications for a later visit", () => {
  let pushOffers = 0;
  let claim = false;
  const onPush = () => { pushOffers++; };
  const onInstall = (event: Event) => { if (claim) event.preventDefault(); };
  window.addEventListener(PUSH_PROMPT_EVENT, onPush);
  window.addEventListener(INSTALL_PROMPT_EVENT, onInstall);
  try {
    // An ineligible device leaves the moment untouched; saves still offer notifications.
    assert.equal(offerInstallPrompt(), false);
    offerPushNotifications("token");
    assert.equal(pushOffers, 1);

    claim = true;
    assert.equal(offerInstallPrompt(), true);
    assert.equal(offerInstallPrompt(), false, "only one install offer per visit");
    offerPushNotifications("token");
    assert.equal(pushOffers, 1);
  } finally {
    window.removeEventListener(PUSH_PROMPT_EVENT, onPush);
    window.removeEventListener(INSTALL_PROMPT_EVENT, onInstall);
  }
});
