import test from "node:test";
import assert from "node:assert/strict";
import "./test-dom";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { AdminQueue, AdminQueueList } from "./admin-queue";

test("queues start collapsed and page through decisions, including a shrinking last page", async () => {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  const render = (count: number) => (
    <AdminQueue header={<h2>Suspended builds</h2>}>
      <AdminQueueList className="decisions" label="Builds">
        {Array.from({ length: count }, (_, index) => <article key={index}>Build {index + 1}</article>)}
      </AdminQueueList>
    </AdminQueue>
  );
  try {
    await act(async () => root.render(render(6)));
    assert.equal(container.querySelector("details")?.open, false);
    assert.equal(container.querySelector("details")?.getAttribute("name"), "admin-queues");
    assert.equal(container.querySelectorAll("article").length, 5);
    const buttons = container.querySelectorAll("button");
    assert.equal(buttons[0].disabled, true);
    await act(async () => buttons[1].click());
    assert.equal(container.querySelectorAll("article").length, 1);
    assert.equal(container.querySelector("article")?.textContent, "Build 6");
    await act(async () => root.render(render(5)));
    assert.equal(container.querySelectorAll("article").length, 5);
    assert.equal(container.querySelector("nav"), null);
  } finally {
    await act(async () => root.unmount());
    container.remove();
  }
});
