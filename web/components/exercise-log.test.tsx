import test from "node:test";
import assert from "node:assert/strict";

import "./test-dom";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { renderToStaticMarkup } from "react-dom/server";

import { ExerciseLogProvider, type ExerciseLogging } from "./exercise-log";
import { ExerciseRow } from "./structured-plan-renderer";
import type { ExerciseLogRecord, ExerciseLogRequest, StructuredBlock } from "@/lib/types";

const deadlift: StructuredBlock = {
  block_id: "blk-deadlift",
  block_type: "strength",
  display_name: "Trap Bar Deadlift",
  sets: 4,
  reps: 8,
  effort: { method: "RPE", value: 7 },
};

const plank: StructuredBlock = {
  block_id: "blk-plank",
  block_type: "accessory",
  display_name: "Front Plank",
  duration: { value: 3, unit: "minutes" },
};

function record(block: StructuredBlock, patch: Partial<ExerciseLogRecord> = {}): ExerciseLogRecord {
  return {
    id: "log-1",
    athlete_id: "athlete-1",
    plan_id: "plan-1",
    session_id: "s1",
    block_id: block.block_id ?? "",
    exercise_key: null,
    training_day: "2026-10-12",
    status: "as_prescribed",
    reason: null,
    prescribed: block,
    actual: {},
    notes: "",
    created_at: "",
    updated_at: "",
    ...patch,
  };
}

type Saved = Omit<ExerciseLogRequest, "plan_id">;

/** Mounts one open row with live logging and returns what it saved. */
function mount(
  block: StructuredBlock,
  options: {
    logs?: Record<string, ExerciseLogRecord>;
    painReasonAllowed?: boolean;
    fail?: string;
    open?: boolean;
  } = {},
) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const saved: Saved[] = [];
  const errors: string[] = [];
  let toggles = 0;
  let logs = options.logs ?? {};
  let root: Root;
  const render = () => {
    const logging: ExerciseLogging = {
      logs,
      painReasonAllowed: options.painReasonAllowed ?? true,
      onError: (message) => errors.push(message),
      save: async (request) => {
        if (options.fail) {
          throw new Error(options.fail);
        }
        saved.push(request);
        logs = {
          ...logs,
          [request.block_id]: record(block, {
            status: request.status,
            reason: request.reason ?? null,
            actual: request.actual ?? {},
          }),
        };
        render();
      },
    };
    root.render(
      <ExerciseLogProvider logging={logging}>
        <ExerciseRow block={block} open={options.open ?? true} onToggle={() => (toggles += 1)} />
      </ExerciseLogProvider>,
    );
  };
  act(() => {
    root = createRoot(container);
    render();
  });
  const button = (name: string) =>
    Array.from(container.querySelectorAll("button")).find((node) => node.textContent?.trim() === name);
  const press = async (target: Element) => {
    await act(async () => {
      target.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
    });
  };
  const click = async (name: string) => {
    const target = button(name);
    assert.ok(target, `button "${name}" not found`);
    await press(target);
  };
  const type = async (label: string, value: string) => {
    const field = Array.from(container.querySelectorAll("label")).find((node) =>
      node.textContent?.startsWith(label),
    );
    const input = field?.querySelector("input");
    assert.ok(input, `input "${label}" not found`);
    await act(async () => {
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value")!.set!;
      setter.call(input, value);
      input.dispatchEvent(new window.Event("input", { bubbles: true }));
    });
  };
  return {
    container,
    saved,
    errors,
    toggled: () => toggles,
    button,
    press,
    click,
    type,
    text: () => container.textContent ?? "",
    unmount: () => {
      act(() => root.unmount());
      container.remove();
    },
  };
}

test("a row renders no log controls unless a started session provides logging", () => {
  const html = renderToStaticMarkup(<ExerciseRow block={deadlift} open onToggle={() => {}} />);
  assert.equal(html.includes("ex-log"), false);

  const closed = renderToStaticMarkup(
    <ExerciseLogProvider logging={null}>
      <ExerciseRow block={deadlift} open onToggle={() => {}} />
    </ExerciseLogProvider>,
  );
  assert.equal(closed.includes("ex-log"), false);
});

test("rehab blocks and blocks without a server id are never loggable", () => {
  const logging: ExerciseLogging = { logs: {}, painReasonAllowed: true, save: async () => {} };
  const render = (block: StructuredBlock) =>
    renderToStaticMarkup(
      <ExerciseLogProvider logging={logging}>
        <ExerciseRow block={block} open onToggle={() => {}} />
      </ExerciseLogProvider>,
    );
  assert.equal(render({ ...deadlift, block_type: "rehab" }).includes("ex-log"), false);
  assert.equal(render({ ...deadlift, block_id: null }).includes("ex-log"), false);
  assert.equal(render(deadlift).includes("ex-log-tick"), true);
});

test("the prescription stays read-only: the stats are not inputs", () => {
  const view = mount(deadlift);
  assert.equal(view.container.querySelectorAll(".sp-block-stats input, .sp-block-stats button.sp-stat").length, 0);
  view.unmount();
});

test("the tick logs a collapsed exercise as written in one tap", async () => {
  const view = mount(deadlift, { open: false });
  const tick = view.container.querySelector<HTMLButtonElement>(".ex-log-tick");
  assert.equal(tick?.getAttribute("aria-label"), "Mark Trap Bar Deadlift done as written");
  await view.press(tick!);

  assert.deepEqual(view.saved, [{ block_id: "blk-deadlift", status: "as_prescribed" }]);
  const logged = view.container.querySelector(".ex-log-tick");
  assert.equal(logged?.getAttribute("data-status"), "as_prescribed");
  assert.equal(logged?.getAttribute("aria-label"), "Trap Bar Deadlift: done. Change");
  // A plain "done" needs no extra line under the name.
  assert.equal(view.container.querySelector(".ex-row-log"), null);
  view.unmount();
});

test("tapping the tick of a logged exercise opens it instead of saving again", async () => {
  const view = mount(deadlift, { open: false, logs: { "blk-deadlift": record(deadlift) } });
  await view.press(view.container.querySelector<HTMLButtonElement>(".ex-log-tick")!);

  assert.deepEqual(view.saved, []);
  assert.equal(view.toggled(), 1);
  view.unmount();
});

test("a failed one-tap save is reported and leaves the exercise unlogged", async () => {
  const view = mount(deadlift, { open: false, fail: "Start today's session before logging an exercise." });
  await view.press(view.container.querySelector<HTMLButtonElement>(".ex-log-tick")!);

  assert.deepEqual(view.errors, ["Start today's session before logging an exercise."]);
  assert.equal(view.container.querySelector(".ex-log-tick")?.hasAttribute("data-status"), false);
  view.unmount();
});

test("one tap inside the open row logs it as written", async () => {
  const view = mount(deadlift);
  await view.click("Done");

  assert.deepEqual(view.saved, [{ block_id: "blk-deadlift", status: "as_prescribed" }]);
  assert.equal(view.container.querySelector(".ex-log-status")?.textContent, "Done");
  assert.ok(view.button("Change"));
  view.unmount();
});

test("logging different numbers saves only the change, with the chosen reason", async () => {
  const view = mount(deadlift);
  await view.click("Log numbers");
  // No reason is asked for until something actually departs from the plan.
  assert.equal(view.container.querySelector(".ex-log-reasons"), null);
  await view.type("Sets", "3");
  await view.type("Load", "80");
  assert.ok(view.container.querySelector(".ex-log-reasons"));
  await view.click("Equipment");
  await view.click("Save");

  assert.deepEqual(view.saved, [
    {
      block_id: "blk-deadlift",
      status: "modified",
      actual: { sets: 3, load: { value: 80, unit: "kg" } },
      reason: "equipment",
    },
  ]);
  // Prescribed and actual on one line.
  assert.equal(
    view.container.querySelector(".ex-log-status")?.textContent,
    "Changed3 sets not 480 kgEquipment",
  );
  view.unmount();
});

test("adding the weight used does not turn the log into a change", async () => {
  const view = mount(deadlift);
  await view.click("Log numbers");
  await view.type("Load", "100");
  await view.click("Save");

  assert.deepEqual(view.saved, [
    { block_id: "blk-deadlift", status: "as_prescribed", actual: { load: { value: 100, unit: "kg" } }, reason: null },
  ]);
  view.unmount();
});

test("an entry far from the prescription is confirmed before it is saved", async () => {
  const view = mount(plank);
  await view.click("Log numbers");
  await view.type("Duration", "15");
  await view.click("Save");

  assert.deepEqual(view.saved, []);
  assert.equal(view.container.querySelector(".ex-log-confirm")?.textContent, "15 min against 3 prescribed?");

  await view.click("Yes, save");
  assert.deepEqual(view.saved, [
    {
      block_id: "blk-plank",
      status: "modified",
      actual: { duration: { value: 15, unit: "minutes" } },
      reason: null,
    },
  ]);
  view.unmount();
});

test("changing the number after the prompt asks again instead of saving", async () => {
  const view = mount(plank);
  await view.click("Log numbers");
  await view.type("Duration", "15");
  await view.click("Save");
  await view.type("Duration", "150");
  assert.equal(view.container.querySelector(".ex-log-confirm"), null);
  await view.click("Save");

  assert.deepEqual(view.saved, []);
  assert.equal(view.container.querySelector(".ex-log-confirm")?.textContent?.includes("150 min"), true);
  view.unmount();
});

test("an unusable number is pointed at and nothing is saved", async () => {
  const view = mount(deadlift);
  await view.click("Log numbers");
  await view.type("Sets", "abc");
  await view.click("Save");

  assert.deepEqual(view.saved, []);
  assert.equal(view.container.querySelector('[role="alert"]')?.textContent, "Check Sets.");
  assert.equal(view.container.querySelector('input[aria-invalid="true"]') !== null, true);
  view.unmount();
});

test("skipping saves in one tap; the reason is a second, optional tap", async () => {
  const view = mount(deadlift);
  await view.click("Skip");
  assert.deepEqual(view.saved, [{ block_id: "blk-deadlift", status: "skipped" }]);
  // Nobody skips because they felt strong.
  assert.equal(view.button("Strong"), undefined);

  await view.click("Fatigue");
  assert.deepEqual(view.saved[1], { block_id: "blk-deadlift", status: "skipped", reason: "fatigue" });
  assert.equal(view.button("Fatigue")?.getAttribute("aria-pressed"), "true");
  view.unmount();
});

test("the pain reason is only offered with health consent", async () => {
  const withConsent = mount(deadlift);
  await withConsent.click("Skip");
  assert.ok(withConsent.button("Pain"));
  withConsent.unmount();

  const without = mount(deadlift, { painReasonAllowed: false });
  await without.click("Skip");
  assert.equal(without.button("Pain"), undefined);
  assert.ok(without.button("Fatigue"));
  without.unmount();
});

test("a saved log can be changed to a different outcome", async () => {
  const view = mount(deadlift, {
    logs: { "blk-deadlift": record(deadlift, { status: "modified", actual: { sets: 3 }, reason: "fatigue" }) },
  });
  assert.equal(view.container.querySelector(".ex-log-status")?.textContent, "Changed3 sets not 4Fatigue");
  await view.click("Change");
  await view.click("Log numbers");
  // The editor opens on what was saved.
  const sets = view.container.querySelector<HTMLInputElement>(".ex-log-field input");
  assert.equal(sets?.value, "3");
  await view.click("Cancel");
  await view.click("Change");
  await view.click("Done");

  assert.deepEqual(view.saved, [{ block_id: "blk-deadlift", status: "as_prescribed" }]);
  view.unmount();
});

test("a failed save keeps the entry and shows the server's message", async () => {
  const view = mount(deadlift, { fail: "Start today's session before logging an exercise." });
  await view.click("Log numbers");
  await view.type("Sets", "3");
  await view.click("Save");

  assert.equal(
    view.container.querySelector('[role="alert"]')?.textContent,
    "Start today's session before logging an exercise.",
  );
  assert.equal(view.container.querySelector<HTMLInputElement>(".ex-log-field input")?.value, "3");
  view.unmount();
});

test("a collapsed row carries the numbers that were logged", () => {
  const logging: ExerciseLogging = {
    logs: { "blk-deadlift": record(deadlift, { status: "modified", actual: { sets: 3, load: { value: 80, unit: "kg" } } }) },
    painReasonAllowed: true,
    save: async () => {},
  };
  const html = renderToStaticMarkup(
    <ExerciseLogProvider logging={logging}>
      <ExerciseRow block={deadlift} open={false} onToggle={() => {}} />
      <ExerciseRow block={plank} open={false} onToggle={() => {}} />
    </ExerciseLogProvider>,
  );
  assert.equal(html.includes('class="ex-row-log" data-status="modified">Changed · 3 sets · 80 kg<'), true);
  assert.equal(html.split('class="ex-row-log"').length - 1, 1);
});
