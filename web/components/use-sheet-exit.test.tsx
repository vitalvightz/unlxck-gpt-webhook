import assert from "node:assert/strict";
import test from "node:test";
import "./test-dom";
import { act } from "react";
import { createRoot } from "react-dom/client";

import { SHEET_EXIT_MS, useSheetExit } from "@/lib/use-sheet-exit";

const wait = (ms: number) => act(async () => { await new Promise((resolve) => setTimeout(resolve, ms)); });

async function mount(onDismiss: (reason: string) => void) {
  const latest: { closing: boolean; close: ((reason: string) => void) | null } = { closing: false, close: null };
  function Sheet() {
    const { closing, close } = useSheetExit(onDismiss);
    latest.closing = closing;
    latest.close = close;
    return <div data-closing={closing || undefined} />;
  }
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => root.render(<Sheet />));
  return { latest, cleanup: () => { act(() => root.unmount()); container.remove(); } };
}

test("closing marks the sheet at once, and tells the parent only after it has slid away", async () => {
  const dismissed: string[] = [];
  const ui = await mount((reason) => dismissed.push(reason));
  try {
    act(() => ui.latest.close!("done"));
    assert.equal(ui.latest.closing, true);
    assert.deepEqual(dismissed, []);
    act(() => ui.latest.close!("again"));
    await wait(SHEET_EXIT_MS + 20);
    assert.deepEqual(dismissed, ["done"], "a second tap while closing does not dismiss twice");
    // The parent kept the sheet (it asked to confirm, say): it shows again.
    assert.equal(ui.latest.closing, false);
  } finally {
    ui.cleanup();
  }
});

test("with reduced motion a sheet closes at once", async () => {
  const matchMedia = window.matchMedia;
  const setMatchMedia = (value: typeof window.matchMedia) =>
    Object.defineProperty(window, "matchMedia", { configurable: true, value });
  setMatchMedia(((query: string) => ({ matches: query.includes("reduce"), media: query,
    addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {}, onchange: null,
    dispatchEvent: () => false })) as typeof window.matchMedia);
  const dismissed: string[] = [];
  const ui = await mount((reason) => dismissed.push(reason));
  try {
    act(() => ui.latest.close!("now"));
    assert.deepEqual(dismissed, ["now"]);
    assert.equal(ui.latest.closing, false);
  } finally {
    ui.cleanup();
    setMatchMedia(matchMedia);
  }
});
