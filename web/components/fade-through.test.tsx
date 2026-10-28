import assert from "node:assert/strict";
import test from "node:test";
import "./test-dom";
import { act } from "react";
import { createRoot } from "react-dom/client";

import { FadeThroughProvider, useFadeThrough, type FadeThrough } from "./fade-through";

const wait = (ms: number) => act(async () => { await new Promise((resolve) => setTimeout(resolve, ms)); });

async function mount() {
  const latest: { fade: FadeThrough | null } = { fade: null };
  function Probe({ onRender }: { onRender: (fade: FadeThrough) => void }) {
    onRender(useFadeThrough());
    return null;
  }
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => root.render(<FadeThroughProvider><Probe onRender={(fade) => { latest.fade = fade; }} /></FadeThroughProvider>));
  return {
    fade: () => latest.fade!,
    phase: () => container.querySelector<HTMLElement>(".fade-through")?.dataset.phase ?? "idle",
    cleanup: () => { act(() => root.unmount()); container.remove(); },
  };
}

test("a change waits for the screen to go black, then the black fades away", async () => {
  const ui = await mount();
  try {
    const order: string[] = [];
    act(() => ui.fade()(() => order.push("swap")));
    assert.equal(ui.phase(), "covering");
    assert.deepEqual(order, [], "nothing changes while it is still going dark");
    await wait(140);
    assert.deepEqual(order, ["swap"]);
    await wait(320);
    assert.equal(ui.phase(), "idle");
  } finally {
    ui.cleanup();
  }
});

test("changes asked for while going dark swap together in one fade", async () => {
  const ui = await mount();
  try {
    const order: string[] = [];
    act(() => {
      ui.fade()(() => order.push("timer closes"));
      ui.fade()(() => order.push("review opens"));
    });
    await wait(60);
    act(() => ui.fade()(() => order.push("sparring sheet")));
    assert.deepEqual(order, []);
    await wait(100);
    assert.deepEqual(order, ["timer closes", "review opens", "sparring sheet"]);
  } finally {
    ui.cleanup();
  }
});

test("without the provider a change happens at once", async () => {
  let fade: FadeThrough | null = null;
  function Probe() { fade = useFadeThrough(); return null; }
  const container = document.createElement("div");
  const root = createRoot(container);
  await act(async () => root.render(<Probe />));
  let changed = false;
  fade!(() => { changed = true; });
  assert.equal(changed, true);
  act(() => root.unmount());
});
