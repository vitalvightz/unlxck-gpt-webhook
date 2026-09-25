import test from "node:test";
import assert from "node:assert/strict";

import "../test-dom";
import { act } from "react";
import { createRoot } from "react-dom/client";

import TimerPage from "@/app/timer/page";
import { RoundTimerProvider, useRoundTimer } from "./round-timer-provider";

function ShownFlag() {
  return <p data-testid="flag">{useRoundTimer().shown ? "shown" : "hidden"}</p>;
}

test("the round timer opens from the timer page, minimises to its mini bar, and closes", async () => {
  window.localStorage.clear();
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => {
    root.render(
      <RoundTimerProvider>
        <TimerPage />
        <ShownFlag />
      </RoundTimerProvider>,
    );
  });

  const flag = () => container.querySelector('[data-testid="flag"]')?.textContent;
  assert.equal(flag(), "hidden");
  assert.equal(document.querySelector(".st-root"), null);

  const start = [...container.querySelectorAll("button")].find((b) => b.textContent === "Start round timer");
  assert.ok(start);
  await act(async () => start.click());
  assert.equal(flag(), "shown");
  assert.ok(document.querySelector('.st-root[role="dialog"]'));
  assert.ok([...container.querySelectorAll("button")].some((b) => b.textContent === "Open round timer"));

  const minimise = document.querySelector<HTMLButtonElement>('[aria-label="Minimise timer"]');
  assert.ok(minimise);
  await act(async () => minimise.click());
  assert.equal(document.querySelector(".st-root"), null);
  const mini = document.querySelector<HTMLButtonElement>(".st-mini");
  assert.ok(mini);
  assert.equal(flag(), "shown");

  await act(async () => mini.click());
  assert.ok(document.querySelector(".st-root"));

  await act(async () => root.unmount());
  container.remove();
});

test("without a provider the round timer reads as closed", async () => {
  const container = document.createElement("div");
  const root = createRoot(container);
  await act(async () => root.render(<ShownFlag />));
  assert.equal(container.textContent, "hidden");
  await act(async () => root.unmount());
});
