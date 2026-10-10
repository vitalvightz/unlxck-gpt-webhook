import test from "node:test";
import assert from "node:assert/strict";
import { window as domWindow } from "./test-dom";
import { act } from "react";
import { createRoot } from "react-dom/client";

import { ExerciseMediaProvider } from "./exercise-demo";
import { ExerciseLogProvider, type ExerciseLogging } from "./exercise-log";
import { ExerciseRow } from "./structured-plan-renderer";
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
