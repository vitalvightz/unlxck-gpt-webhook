"use client";

// One-shot signal that the user explicitly asked to start a brand-new plan
// generation (e.g. tapped "Generate" at the end of intake or quick build).
//
// The /generate page auto-starts work on mount, but mounting can also happen
// for reasons the user never asked for — a backgrounded mobile tab that the OS
// reloaded, a manual refresh, or a deep link. Without an explicit intent
// signal the page can't tell "I just clicked Generate" apart from "my tab
// reopened", and would silently kick off a fresh generation in the latter
// case. We persist intent in sessionStorage so it survives the client-side
// navigation into /generate but is naturally absent on a cold tab restore.
const GENERATION_INTENT_KEY = "unlxck:generation-intent";

export function markGenerationIntent(): void {
  if (typeof window === "undefined") {
    return;
  }
  try {
    window.sessionStorage.setItem(GENERATION_INTENT_KEY, "1");
  } catch {
    // Storage can throw in private-mode/quota edge cases. The worst case is the
    // generate page falls back to recover-only and the user re-triggers from
    // the workspace, which is far safer than an unwanted generation.
  }
}

export function hasGenerationIntent(): boolean {
  if (typeof window === "undefined") {
    return false;
  }
  try {
    return window.sessionStorage.getItem(GENERATION_INTENT_KEY) === "1";
  } catch {
    return false;
  }
}

export function clearGenerationIntent(): void {
  if (typeof window === "undefined") {
    return;
  }
  try {
    window.sessionStorage.removeItem(GENERATION_INTENT_KEY);
  } catch {
    // Ignore — a stale intent is cleared again on the next terminal branch.
  }
}
