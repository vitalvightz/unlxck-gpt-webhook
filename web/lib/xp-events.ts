export const XP_REFRESH_EVENT = "unlxck:xp-refresh";

export function requestXpRefresh(): void {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event(XP_REFRESH_EVENT));
  }
}
