import assert from "node:assert/strict";
import test from "node:test";
import "../test-dom";
import { act, useState } from "react";
import { createRoot } from "react-dom/client";

import { COLLAPSE_EXIT_MS, Collapse } from "./collapse";

async function mount(initial: boolean) {
  let setShow: (show: boolean) => void = () => {};
  function Harness() {
    const [show, set] = useState(initial);
    setShow = set;
    return <Collapse show={show}>{show ? <p>Follow-up</p> : null}</Collapse>;
  }
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => root.render(<Harness />));
  return {
    container,
    wrapper: () => container.querySelector<HTMLElement>(".today-collapse"),
    show: (next: boolean) => act(async () => setShow(next)),
    cleanup: () => { act(() => root.unmount()); container.remove(); },
  };
}

test("a section shown on first render does not animate open", async () => {
  const ui = await mount(true);
  try {
    assert.equal(ui.wrapper()?.dataset.phase, "open");
  } finally {
    ui.cleanup();
  }
});

test("opening eases in; closing keeps the last content, inert, until the exit ends", async () => {
  const ui = await mount(false);
  try {
    assert.equal(ui.wrapper(), null);
    await ui.show(true);
    assert.equal(ui.wrapper()?.dataset.phase, "entering");
    assert.match(ui.container.textContent ?? "", /Follow-up/);

    // The caller drops the content at once; it stays as a fading picture.
    await ui.show(false);
    assert.equal(ui.wrapper()?.dataset.phase, "leaving");
    assert.equal(ui.wrapper()?.hasAttribute("inert"), true);
    assert.equal(ui.wrapper()?.getAttribute("aria-hidden"), "true");
    assert.match(ui.container.textContent ?? "", /Follow-up/);

    // Its own exit animation ending is what removes it.
    await act(async () => { ui.wrapper()!.dispatchEvent(new window.Event("animationend", { bubbles: true })); });
    assert.equal(ui.wrapper(), null);
  } finally {
    ui.cleanup();
  }
});

test("a closing section still goes if its exit animation never reports ending", async () => {
  const ui = await mount(true);
  try {
    await ui.show(false);
    assert.equal(ui.wrapper()?.dataset.phase, "leaving");
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, COLLAPSE_EXIT_MS + 200)); });
    assert.equal(ui.wrapper(), null);
  } finally {
    ui.cleanup();
  }
});

test("reopening mid-exit brings the section straight back", async () => {
  const ui = await mount(true);
  try {
    await ui.show(false);
    await ui.show(true);
    assert.equal(ui.wrapper()?.dataset.phase, "entering");
    assert.equal(ui.wrapper()?.hasAttribute("inert"), false);
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, COLLAPSE_EXIT_MS + 200)); });
    assert.notEqual(ui.wrapper(), null);
  } finally {
    ui.cleanup();
  }
});
