import test from "node:test";
import assert from "node:assert/strict";
import { window as domWindow } from "./test-dom";
import { act } from "react";
import { createRoot } from "react-dom/client";

import { ExerciseMediaProvider } from "./exercise-demo";
import { ExerciseLogProvider, type ExerciseLogging } from "./exercise-log";
import { ExerciseRow } from "./structured-plan-renderer";
import { readFileSync } from "node:fs";
import type { ExerciseMedia, StructuredBlock } from "@/lib/types";

const treadmill: StructuredBlock = {
  block_id: "treadmill",
  block_type: "conditioning",
  display_name: "Incline treadmill walk intervals",
  effort: { method: "RPE", value: 5 },
  coaching_cues: ["Stay tall, no rail."],
};

const demo: ExerciseMedia = { provider: "youtube", video_id: "dQw4w9WgXcQ", start_s: 63, end_s: 78, source: "curated" };

const logging: ExerciseLogging = { logs: {}, save: async () => {}, painReasonAllowed: false };

/** Opens the treadmill exercise in its sheet and returns the sheet's sections. */
async function openSheet(sessionRunning: boolean, block: StructuredBlock = treadmill) {
  const container = domWindow.document.createElement("div");
  domWindow.document.body.append(container);
  const root = createRoot(container);
  await act(async () => {
    root.render(
      <ExerciseMediaProvider media={{ [treadmill.display_name!]: demo }}>
        <ExerciseLogProvider logging={sessionRunning ? logging : null}>
          <ExerciseRow block={block} open detail="sheet" onToggle={() => {}} />
        </ExerciseLogProvider>
      </ExerciseMediaProvider>,
    );
  });
  const dialogs = domWindow.document.querySelectorAll('[role="dialog"]');
  const sheet = dialogs[dialogs.length - 1];
  const sections = [...sheet.querySelectorAll<HTMLDetailsElement>("details.ex-detail-section")];
  const byTitle = (title: string) => sections.find((section) => section.querySelector("summary")?.textContent === title);
  return {
    sheet,
    byTitle,
    others: sections.filter((section) => section.querySelector("summary")?.textContent !== "Demo video"),
    cleanup: async () => {
      await act(async () => root.unmount());
      container.remove();
    },
  };
}

test("in a preview the demo section starts open, paused on its tap-to-play frame", async () => {
  const { sheet, byTitle, others, cleanup } = await openSheet(false);
  try {
    const demoSection = byTitle("Demo video");
    assert.ok(demoSection);
    assert.equal(demoSection.open, true);
    // Paused: the facade (thumbnail + play button) shows; no player is loaded.
    assert.ok(sheet.querySelector('button[aria-label="Play Incline treadmill walk intervals demo"]'));
    assert.equal(sheet.querySelector(".ex-demo-player"), null);
    assert.ok(others.length > 0);
    assert.ok(others.every((section) => !section.open));
  } finally {
    await cleanup();
  }
});

test("once the session is running the sheet shows only the prescription and the log", async () => {
  const { sheet, byTitle, cleanup } = await openSheet(true);
  try {
    assert.equal(byTitle("Demo video"), undefined);
    assert.equal(byTitle("Why it's here"), undefined);
    assert.ok(sheet.querySelector(".ex-detail-prescription"));
    assert.ok(sheet.querySelector(".ex-log"));
  } finally {
    await cleanup();
  }
});

test("the stop rule stays visible in the logging sheet while coaching stays hidden", async () => {
  const { sheet, byTitle, cleanup } = await openSheet(true, { ...treadmill, stop_rules: ["Stop for dizziness."] });
  try {
    const stop = sheet.querySelector(".ex-detail-stop");
    assert.ok(stop);
    assert.match(stop.textContent ?? "", /Stop if dizziness/);
    assert.equal(stop.closest("details"), null);
    assert.ok(sheet.querySelector(".ex-log"));
    assert.equal(byTitle("Demo video"), undefined);
    assert.equal(byTitle("Why it's here"), undefined);
    assert.doesNotMatch(sheet.textContent ?? "", /Stay tall, no rail\./);
  } finally {
    await cleanup();
  }
});

test("October 15 punch keeps its complete cue once, including reset, video and exact statistics", async () => {
  const records = JSON.parse(readFileSync("../tests/fixtures/concise_coaching/october_11_15.json", "utf8"));
  const saved = records[1].card.weeks.flatMap((w: { days: { sessions: { blocks: StructuredBlock[] }[] }[] }) =>
    w.days.flatMap(d => d.sessions.flatMap(s => s.blocks)))
    .find((b: StructuredBlock) => b.display_name === "Band-Resisted Punch") as StructuredBlock;
  // Same compact fields asserted against actual backend recovery in the Python replay.
  const block = { ...saved, coaching_cues: ["Keep punches balanced; return to guard", ...saved.coaching_cues!],
    regression_options: [saved.regression_options![0]],
    stop_rules: ["Stop if punch speed worsens, guard return fails, balance deteriorates, or pain appears."] };
  const container = domWindow.document.createElement("div");
  domWindow.document.body.append(container);
  const root = createRoot(container);
  try {
    await act(async () => root.render(
      <ExerciseMediaProvider media={{ [`exercise:${block.exercise_key}`]: demo }}>
        <ExerciseRow block={block} open onToggle={() => {}} />
      </ExerciseMediaProvider>,
    ));
    assert.equal(container.querySelector(".ex-demo-lead-cue")?.textContent,
      "Key cueKeep punches balanced; return to guard and reset stance between exchanges");
    assert.equal(container.querySelector("details.ex-detail-section"), null);
    assert.equal(container.textContent?.split("Keep punches balanced; return to guard").length, 2);
    assert.equal(container.textContent?.split("reset stance between exchanges").length, 2);
    assert.ok(container.querySelector('button[aria-label="Play Band-Resisted Punch demo"]'));
    assert.ok(container.textContent?.includes("1 × 2"));
    assert.ok(container.textContent?.includes("2 min")); // same 120-second rest
    assert.equal(container.querySelectorAll('[data-kind="stop"]').length, 1);
    const asides = [...container.querySelectorAll(".sp-block-aside")];
    assert.equal(asides.filter(el => el.textContent?.startsWith("Easier")).length, 1);
    assert.equal(asides.filter(el => el.textContent?.startsWith("Progress")).length, 0);
  } finally {
    await act(async () => root.unmount());
    container.remove();
  }
});


test("sheet shows saved swaps, Easier and Progress once", async () => {
  const { sheet, byTitle, cleanup } = await openSheet(false, { ...treadmill,
    coaching_cues: ["Stay tall, no rail.", "Stay tall, no rail."],
    regression_options: ["Reduce rounds to 3."],
    substitutions: ["Easy bike intervals"],
    progression_rule: "Next D-28: add 1 round if recovered.",
    stop_rules: ["Stop for dizziness."],
  });
  try {
    assert.equal(byTitle("Coaching cues"), undefined);
    const lines = [...sheet.querySelectorAll(".sp-block-aside")];
    for (const label of ["Cue", "Easier", "Swaps", "Progress"]) {
      const matching = lines.filter(line => line.querySelector(".sp-stat-label")?.textContent === label);
      assert.equal(matching.length, 1, label);
      assert.equal(matching[0].closest("details"), null, label);
    }
    assert.equal(sheet.textContent?.split("Stay tall, no rail.").length, 2);
    assert.match(sheet.textContent ?? "", /Next D-28: add 1 round if recovered/);
    assert.ok(sheet.textContent?.includes("Easy bike intervals"));
    assert.match(sheet.querySelector(".ex-detail-stop")?.textContent ?? "", /dizziness/);
    assert.equal(lines.filter(line => line.querySelector(".sp-stat-label")?.textContent === "Progress").length, 1);
  } finally { await cleanup(); }
});

for (const running of [false, true]) {
  test(`without a demo How and rest remain available ${running ? "during logging" : "in preview"}`, async () => {
    const instruction = "Parry once, throw the cross, then step out of range.";
    const progress = "At the same dose, keep your exits clean.";
    const { sheet, byTitle, cleanup } = await openSheet(running, {
      block_id: "no-demo", display_name: "Parry-Cross-Exit", block_type: "skill",
      rounds: 3, work: { value: 5, unit: "seconds" }, rest: { value: 120, unit: "seconds" },
      execution_instructions: instruction, progression_rule: progress,
      stop_rules: ["Stop if stance breaks."],
    });
    try {
      assert.equal(byTitle("Demo video"), undefined);
      assert.equal(sheet.querySelector(".ex-execution-instructions")?.textContent, `How${instruction}`);
      assert.equal(sheet.textContent?.split(instruction).length, 2);
      const rest = [...sheet.querySelectorAll(".sp-stat")].find(stat => stat.textContent?.startsWith("Rest"));
      assert.equal(rest?.textContent, "Rest2 min");
      assert.equal(sheet.textContent?.includes(progress), !running);
      assert.match(sheet.textContent ?? "", /stance breaks/);
    } finally { await cleanup(); }
  });
}
