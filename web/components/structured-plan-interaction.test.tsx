import test from "node:test";
import assert from "node:assert/strict";

// Installs the jsdom globals for react-dom/client. Must run before the client
// renderer / component are exercised (the import side effect handles that).
import "./test-dom";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";

import { StructuredPlanRenderer } from "./structured-plan-renderer";
import type { StructuredPlan } from "@/lib/types";

// A two-week plan whose weeks sit in different phases.
function twoPhasePlan(): StructuredPlan {
  return {
    schema_version: "1.0",
    plan_metadata: { title: "Fight Camp", sport: "boxing", plan_type: "fight_camp" },
    weeks: [
      {
        week_id: "wk-1",
        week_index: 1,
        phase_label: "GPP",
        days: [{ date: "2026-06-15", day_type: "moderate", sessions: [] }],
      },
      {
        week_id: "wk-2",
        week_index: 2,
        phase_label: "TAPER",
        days: [{ date: "2026-06-22", day_type: "taper", sessions: [] }],
      },
    ],
  } as StructuredPlan;
}

// A structurally different plan (one week, different id) — used to prove a plan
// swap resets the retained week selection instead of pointing at a stale index.
function singlePhasePlan(): StructuredPlan {
  return {
    schema_version: "1.0",
    plan_metadata: { title: "New Camp", sport: "boxing", plan_type: "fight_camp" },
    weeks: [
      {
        week_id: "swap-wk-1",
        week_index: 1,
        phase_label: "SPP",
        days: [{ date: "2026-07-01", day_type: "moderate", sessions: [] }],
      },
    ],
  } as StructuredPlan;
}

function mount(): { container: HTMLElement; root: Root } {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  return { container, root };
}

function cleanup(container: HTMLElement, root: Root) {
  act(() => {
    root.unmount();
  });
  container.remove();
}

function weekPillByPhase(container: HTMLElement, phase: string): HTMLButtonElement {
  const pill = Array.from(container.querySelectorAll<HTMLButtonElement>("button.cm-week-pill")).find(
    (el) => (el.textContent ?? "").toLowerCase().includes(phase.toLowerCase()),
  );
  assert.ok(pill, `expected a week pill for phase "${phase}"`);
  return pill;
}

test("open-plan overview follows the selected week instead of the current calendar week", async () => {
  const { container, root } = mount();
  const plan = {
    schema_version: "1.0",
    plan_metadata: {
      title: "Open Plan",
      sport: "boxing",
      plan_type: "open_ongoing_system",
    },
    weeks: [1, 2, 3, 4].map((weekIndex) => ({
      week_id: `wk-${weekIndex}`,
      week_index: weekIndex,
      phase_label: "GPP",
      week_goal: `Goal ${weekIndex}`,
      days: [],
    })),
  } as StructuredPlan;

  try {
    await act(async () => {
      root.render(
        <StructuredPlanRenderer
          plan={plan}
          openOngoing
          scheduleContext={{
            schedule_mode: "open_recurring",
            projection_status: "projected",
            block_number: 1,
            current_week_number: 1,
          }}
        />,
      );
    });

    const weekTwo = Array.from(
      container.querySelectorAll<HTMLButtonElement>("button.cm-week-pill"),
    ).find((button) => (button.textContent ?? "").includes("W2"));
    assert.ok(weekTwo, "expected a W2 control");

    await act(async () => {
      weekTwo.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
    });

    const overview = container.querySelector(".cm-week-overview h2")?.textContent ?? "";
    assert.equal(overview.includes("Block 1 · Week 2 of 4"), true);
  } finally {
    cleanup(container, root);
  }
});

test("swapping in a structurally different plan resets the stale week selection", async () => {
  const { container, root } = mount();
  try {
    await act(async () => {
      root.render(<StructuredPlanRenderer plan={twoPhasePlan()} />);
    });

    // Select the second week (index 1) on the two-week plan.
    await act(async () => {
      weekPillByPhase(container, "taper").dispatchEvent(
        new window.MouseEvent("click", { bubbles: true }),
      );
    });
    assert.equal(
      (container.querySelector("button.cm-week-pill-selected")?.textContent ?? "").toLowerCase().includes("taper"),
      true,
    );

    // Swap to a one-week plan WITHOUT remounting. A retained selectedPos of 1
    // would be out of range / point at the wrong week; the render-time reset must
    // drop it so the new plan lands on its own first week (SPP), never a flash of
    // the old index or an empty week.
    await act(async () => {
      root.render(<StructuredPlanRenderer plan={singlePhasePlan()} />);
    });

    const pills = container.querySelectorAll("button.cm-week-pill");
    assert.equal(pills.length, 1, "the swapped plan has a single week");
    // The selected pill is the new plan's only week (no stale selection carried).
    const selected = container.querySelector("button.cm-week-pill-selected");
    assert.ok(selected, "a week is selected");
    assert.equal((selected?.textContent ?? "").toLowerCase().includes("specific prep"), true);
  } finally {
    cleanup(container, root);
  }
});

// A dated multi-week plan long enough to make the week rail scroll. Each week
// carries one dated day so current-week resolution can land on a real week.
function manyWeekPlan(count: number): StructuredPlan {
  const isoWeek = (i: number): string => {
    const d = new Date(2026, 5, 1);
    d.setDate(d.getDate() + i * 7);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  };
  return {
    schema_version: "1.0",
    plan_metadata: { title: "Fight Camp", sport: "boxing", plan_type: "fight_camp" },
    weeks: Array.from({ length: count }, (_, i) => ({
      week_id: `wk-${i + 1}`,
      week_index: i + 1,
      phase_label: i === 0 ? "GPP" : i === count - 1 ? "TAPER" : "SPP",
      days: [{ date: isoWeek(i), day_type: "moderate", sessions: [] }],
    })),
  } as StructuredPlan;
}

// jsdom performs no layout, so element geometry is fed in explicitly. This lets
// the rail's scroll effect run against realistic numbers.
function stubGeometry(el: Element, values: Partial<Record<"clientWidth" | "scrollWidth" | "offsetLeft", number>>) {
  for (const [key, value] of Object.entries(values)) {
    Object.defineProperty(el, key, { configurable: true, get: () => value });
  }
}

test("selecting an off-screen week scrolls the rail to centre it", async () => {
  const { container, root } = mount();
  try {
    // A real current week exists (today matches week 0). Centring must still
    // follow the *selected* week, not stay pinned to "now" — otherwise tapping a
    // far card leaves it half cut off. manyWeekPlan(0)'s day is 2026-06-01.
    await act(async () => {
      root.render(<StructuredPlanRenderer plan={manyWeekPlan(8)} today={new Date(2026, 5, 1)} />);
    });

    const strip = container.querySelector<HTMLElement>(".cm-week-strip");
    assert.ok(strip, "the rail is present");
    // Week 0 is genuinely the current week (this is what would mask the bug if
    // centring preferred currentPos over selectedPos).
    assert.equal(
      container.querySelector("button.cm-week-pill-current")?.getAttribute("data-week-pos"),
      "0",
    );

    // Make the rail overflow (scrollWidth > clientWidth) and give the target
    // week a known position, plus a capturable scrollLeft.
    let scrollLeft = 0;
    Object.defineProperty(strip!, "scrollLeft", {
      configurable: true,
      get: () => scrollLeft,
      set: (v: number) => {
        scrollLeft = v;
      },
    });
    stubGeometry(strip!, { clientWidth: 300, scrollWidth: 1000 });
    const target = container.querySelector<HTMLButtonElement>('[data-week-pos="6"]');
    assert.ok(target, "the seventh week card is present");
    stubGeometry(target!, { offsetLeft: 700, clientWidth: 80 });

    await act(async () => {
      target!.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
    });

    // Centred on the newly selected week, even though week 0 is still "current":
    // offsetLeft - (clientWidth - pillWidth) / 2 = 700 - (300 - 80) / 2.
    assert.equal(scrollLeft, 700 - (300 - 80) / 2);
    // Selection still works: the clicked week is the selected card.
    const selected = container.querySelector("button.cm-week-pill-selected");
    assert.equal(selected?.getAttribute("data-week-pos"), "6");
  } finally {
    cleanup(container, root);
  }
});

test("current week shortcut restores selection after browsing another week", async () => {
  const { container, root } = mount();
  try {
    await act(async () => {
      root.render(<StructuredPlanRenderer plan={manyWeekPlan(8)} today={new Date(2026, 5, 1)} />);
    });
    assert.equal(container.querySelector(".cm-current-week"), null);
    const later = container.querySelector<HTMLButtonElement>('[data-week-pos="6"]');
    assert.ok(later);
    await act(async () => later.click());
    assert.equal(container.querySelector(".cm-week-navigation-label")?.textContent, "Week 7 of 8");
    const returnButton = container.querySelector<HTMLButtonElement>(".cm-current-week");
    assert.ok(returnButton);
    await act(async () => returnButton.click());
    assert.equal(container.querySelector(".cm-week-pill-selected")?.getAttribute("data-week-pos"), "0");
    assert.equal(container.querySelector(".cm-week-navigation-label")?.textContent, "Week 1 of 8");
    assert.equal(container.querySelector(".cm-current-week"), null);
  } finally {
    cleanup(container, root);
  }
});

test("the rail does not scroll (or throw) when it fits without overflow", async () => {
  const { container, root } = mount();
  try {
    await act(async () => {
      root.render(<StructuredPlanRenderer plan={manyWeekPlan(3)} />);
    });

    const strip = container.querySelector<HTMLElement>(".cm-week-strip");
    assert.ok(strip, "the rail is present");
    // Three weeks share the width — the rail is not marked scrollable.
    assert.equal(strip!.getAttribute("data-scroll"), null);

    let scrollLeft = 0;
    Object.defineProperty(strip!, "scrollLeft", {
      configurable: true,
      get: () => scrollLeft,
      set: (v: number) => {
        scrollLeft = v;
      },
    });
    // clientWidth === scrollWidth (no overflow): the effect must leave it alone.
    stubGeometry(strip!, { clientWidth: 300, scrollWidth: 300 });

    const second = container.querySelector<HTMLButtonElement>('[data-week-pos="1"]');
    await act(async () => {
      second!.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
    });

    assert.equal(scrollLeft, 0);
    assert.equal(container.querySelector("button.cm-week-pill-selected")?.getAttribute("data-week-pos"), "1");
  } finally {
    cleanup(container, root);
  }
});

test("calendar view opens the tapped day back in the list", async () => {
  const { container, root } = mount();
  const plan = {
    schema_version: "1.0",
    plan_metadata: { title: "Fight Camp", sport: "boxing", plan_type: "fight_camp" },
    weeks: [
      {
        week_id: "wk-1",
        week_index: 1,
        days: [{ date: "2026-06-15", sessions: [{ session_id: "a", title: "Strength A", blocks: [] }] }],
      },
      {
        week_id: "wk-2",
        week_index: 2,
        days: [
          { date: "2026-06-22", sessions: [{ session_id: "b", title: "Strength B", blocks: [] }] },
          { date: "2026-06-24", sessions: [{ session_id: "c", title: "Conditioning C", blocks: [] }] },
        ],
      },
    ],
  } as StructuredPlan;
  try {
    window.localStorage.removeItem("unlxck.plan-view");
    await act(async () => {
      root.render(<StructuredPlanRenderer plan={plan} today={new Date(2026, 5, 15)} />);
    });
    const toggle = (label: string) =>
      Array.from(container.querySelectorAll<HTMLButtonElement>(".cm-view-toggle-option")).find(
        (button) => button.textContent === label,
      );
    assert.equal(toggle("List")?.getAttribute("aria-pressed"), "true");

    await act(async () => toggle("Calendar")?.click());
    assert.ok(container.querySelector(".cm-calendar"));
    assert.equal(container.querySelector(".cm-week-strip"), null);
    assert.equal(container.querySelector(".cm-days"), null);
    assert.equal(window.localStorage.getItem("unlxck.plan-view"), "calendar");

    // Wed 24 Jun is week 2, day 1.
    const cell = Array.from(container.querySelectorAll<HTMLButtonElement>("button.cm-cal-cell")).find(
      (button) => (button.textContent ?? "").includes("Wed 24 Jun 2026"),
    );
    assert.ok(cell, "expected a tappable Wed 24 Jun cell");
    await act(async () => cell.click());

    assert.equal(container.querySelector(".cm-calendar"), null);
    assert.equal(container.querySelector(".cm-week-pill-selected")?.getAttribute("data-week-pos"), "1");
    const opened = container.querySelector<HTMLDetailsElement>('.cm-days [data-day-index="1"]');
    assert.equal(opened?.open, true);
    assert.equal(window.localStorage.getItem("unlxck.plan-view"), "list");
  } finally {
    window.localStorage.removeItem("unlxck.plan-view");
    cleanup(container, root);
  }
});
