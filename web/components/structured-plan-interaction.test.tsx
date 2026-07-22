import test from "node:test";
import assert from "node:assert/strict";

// Installs the jsdom globals for react-dom/client. Must run before the client
// renderer / component are exercised (the import side effect handles that).
import "./test-dom";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";

import { StructuredPlanRenderer } from "./structured-plan-renderer";
import type { StructuredPlan } from "@/lib/types";

// A two-week plan whose weeks sit in different phases, each with its own
// deterministic nutrition/recovery phase, so switching weeks should switch which
// support phase is open.
function twoPhasePlan(): StructuredPlan {
  return {
    schema_version: "1.0",
    plan_metadata: { title: "Fight Camp", sport: "boxing", plan_type: "fight_camp" },
    deterministic_support: {
      nutrition: {
        by_phase: {
          GPP: { meal_structure: "GPP: 4 meals + 2 snacks" },
          TAPER: { meal_structure: "TAPER: 3 meals, lighter" },
        },
      },
      recovery: {
        by_phase: {
          GPP: { sleep_hours_target: [8, 9] },
          TAPER: { sleep_hours_target: [9, 10] },
        },
      },
    },
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
    deterministic_support: {
      nutrition: { by_phase: { SPP: { meal_structure: "SPP: 5 meals" } } },
    },
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

// The open <details> among the phase cards matching a class, by phase substring.
function openPhaseTitles(container: HTMLElement, phaseClass: string): string[] {
  return Array.from(container.querySelectorAll<HTMLDetailsElement>(`details.${phaseClass}`))
    .filter((el) => el.open)
    .map((el) => el.querySelector(".sp-collapse-title")?.textContent?.toLowerCase() ?? "");
}

function weekPillByPhase(container: HTMLElement, phase: string): HTMLButtonElement {
  const pill = Array.from(container.querySelectorAll<HTMLButtonElement>("button.cm-week-pill")).find(
    (el) => (el.textContent ?? "").toLowerCase().includes(phase.toLowerCase()),
  );
  assert.ok(pill, `expected a week pill for phase "${phase}"`);
  return pill;
}

test("selecting a different week re-opens the matching support phase after mount", async () => {
  const { container, root } = mount();
  try {
    await act(async () => {
      root.render(<StructuredPlanRenderer plan={twoPhasePlan()} />);
    });

    // Initial selection falls to the first week (GPP) with no `today` supplied.
    let openNutrition = openPhaseTitles(container, "sp-nutrition-phase");
    let openRecovery = openPhaseTitles(container, "sp-recovery-phase");
    assert.deepEqual(openNutrition, ["general prep"], "GPP nutrition should open on mount");
    assert.deepEqual(openRecovery, ["general prep"], "GPP recovery should open on mount");

    // Click the TAPER week pill — this is a real post-mount interaction, not SSR.
    const taperPill = weekPillByPhase(container, "taper");
    await act(async () => {
      taperPill.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
    });

    // The matching phase re-opens and the previously-active phase closes.
    openNutrition = openPhaseTitles(container, "sp-nutrition-phase");
    openRecovery = openPhaseTitles(container, "sp-recovery-phase");
    assert.deepEqual(openNutrition, ["taper"], "TAPER nutrition should open after switching weeks");
    assert.deepEqual(openRecovery, ["taper"], "TAPER recovery should open after switching weeks");
  } finally {
    cleanup(container, root);
  }
});

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

test("a manual toggle survives until the next week change, then re-syncs", async () => {
  const { container, root } = mount();
  try {
    await act(async () => {
      root.render(<StructuredPlanRenderer plan={twoPhasePlan()} />);
    });

    // Athlete manually opens the non-active TAPER nutrition phase while on GPP.
    const taperDetails = Array.from(
      container.querySelectorAll<HTMLDetailsElement>("details.sp-nutrition-phase"),
    ).find((el) => (el.textContent ?? "").toLowerCase().includes("taper"));
    assert.ok(taperDetails, "expected a TAPER nutrition phase");
    await act(async () => {
      taperDetails.open = true;
      taperDetails.dispatchEvent(new window.Event("toggle", { bubbles: false }));
    });
    // Both are now open: the synced GPP plus the manually-opened TAPER.
    assert.deepEqual(
      openPhaseTitles(container, "sp-nutrition-phase").sort(),
      ["general prep", "taper"],
      "manual open should be preserved before any week change",
    );

    // Changing weeks re-syncs: only the new active phase stays open.
    await act(async () => {
      weekPillByPhase(container, "taper").dispatchEvent(
        new window.MouseEvent("click", { bubbles: true }),
      );
    });
    assert.deepEqual(
      openPhaseTitles(container, "sp-nutrition-phase"),
      ["taper"],
      "week change should re-sync the open phase",
    );
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
    assert.deepEqual(openPhaseTitles(container, "sp-nutrition-phase"), ["taper"]);

    // Swap to a one-week plan WITHOUT remounting. A retained selectedPos of 1
    // would be out of range / point at the wrong week; the render-time reset must
    // drop it so the new plan lands on its own first week (SPP), never a flash of
    // the old index or an empty week.
    await act(async () => {
      root.render(<StructuredPlanRenderer plan={singlePhasePlan()} />);
    });

    const pills = container.querySelectorAll("button.cm-week-pill");
    assert.equal(pills.length, 1, "the swapped plan has a single week");
    assert.deepEqual(
      openPhaseTitles(container, "sp-nutrition-phase"),
      ["specific prep"],
      "the swapped plan opens its own first phase, not a stale index",
    );
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
