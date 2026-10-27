/** A saved workout is the value moment for the one-time device opt-ins. */
export const PUSH_PROMPT_EVENT = "unlxck:session-saved";
/** Dispatched first; the install prompt cancels it when it takes the moment. */
export const INSTALL_PROMPT_EVENT = "unlxck:install-offer";

// Lives for this page visit: once install guidance has taken a moment, the
// notification prompt waits for the next visit instead of following it.
let installClaimed = false;

export function installPromptClaimed(): boolean {
  return installClaimed;
}

export function offerPushNotifications(token: string): void {
  if (installClaimed) return;
  if (!window.dispatchEvent(new CustomEvent(INSTALL_PROMPT_EVENT, { cancelable: true }))) {
    installClaimed = true;
    return;
  }
  window.dispatchEvent(new CustomEvent(PUSH_PROMPT_EVENT, { detail: { token } }));
}
