/** A saved workout is the value moment for the one-time device opt-in. */
export const PUSH_PROMPT_EVENT = "unlxck:session-saved";

export function offerPushNotifications(token: string): void {
  window.dispatchEvent(new CustomEvent(PUSH_PROMPT_EVENT, { detail: { token } }));
}
