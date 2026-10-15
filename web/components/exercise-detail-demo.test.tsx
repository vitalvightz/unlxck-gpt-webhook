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
async function openSheet(sessionRunning: boolean) {
  const container = domWindow.document.createElement("div");
  domWindow.document.body.append(container);
  const root = createRoot(container);
  await act(async () => {
    root.render(
      <ExerciseMediaProvider media={{ [treadmill.display_name!]: demo }}>
        <ExerciseLogProvider logging={sessionRunning ? logging : null}>
          <ExerciseRow block={treadmill} open detail="sheet" onToggle={() => {}} />
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

test("once the session is running the demo section starts collapsed like the rest", async () => {
  const { byTitle, others, cleanup } = await openSheet(true);
  try {
    assert.equal(byTitle("Demo video")?.open, false);
    assert.ok(others.every((section) => !section.open));
  } finally {
    await cleanup();
  }
});

test("October 15 punch keeps its short cue, full expandable detail, video and exact statistics", async () => {
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
      "Key cueKeep punches balanced; return to guard");
    const detail = container.querySelector<HTMLDetailsElement>("details.ex-detail-section")!;
    assert.equal(detail.querySelector("summary")?.textContent, "Full prescription");
    assert.equal(detail.open, false);
    await act(async () => detail.querySelector("summary")!.click());
    assert.equal(detail.open, true);
    assert.ok(container.textContent?.includes("Keep punches balanced; return to guard"));
    assert.equal(container.textContent?.includes("Coaching cues"), false);
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
