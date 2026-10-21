import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import "./test-dom";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { ExerciseMediaProvider } from "./exercise-demo";
import { ExerciseLogProvider } from "./exercise-log";
import { ExerciseRow } from "./structured-plan-renderer";
import type { ExerciseMedia, StructuredBlock } from "@/lib/types";

// Exported by the real Today API; numeric prescriptions are never re-created here.
const fixtures = JSON.parse(readFileSync("e2e/fixtures/rehab-today.json", "utf8"));
const load: StructuredBlock = fixtures.achilles.view.live_prescription.session.blocks[0];
const restore: StructuredBlock = fixtures.chest.view.live_prescription.session.blocks[0];
const demo: ExerciseMedia = { provider: "youtube", video_id: "AAAAAAAAAAA", start_s: 0, source: "curated" };
const bankFixtures = JSON.parse(readFileSync("e2e/fixtures/rehab-bank-publication.json", "utf8"));

async function open(block: StructuredBlock, media: ExerciseMedia | null, running = false) {
  const container = document.createElement("div"); document.body.append(container);
  const root = createRoot(container);
  await act(async () => root.render(<ExerciseMediaProvider media={media ? { [`exercise:${block.exercise_key}`]: media } : {}}>
    <ExerciseLogProvider logging={running ? { logs: {}, save: async () => {}, painReasonAllowed: false } : null}>
      <ExerciseRow block={block} open detail="sheet" onToggle={() => {}} />
    </ExerciseLogProvider>
  </ExerciseMediaProvider>));
  return { sheet: document.querySelector('[role="dialog"]')!, cleanup() { act(() => root.unmount()); container.remove(); } };
}

for (const [pilot, block] of Object.entries(fixtures.pilot_blocks) as Array<[string, StructuredBlock & { instructions: string }]>) {
  test(`${pilot} keeps its exact Today instructions, dose and restrictions in the shared exercise sheet`, async () => {
    const { sheet, cleanup } = await open(block, demo);
    try {
      // The shared renderer places the Stop sentence above the movement cues.
      // Every approved sentence must survive that presentation split.
      const words = (value: string) => value.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
      for (const sentence of block.instructions.split(/(?<=[.!?])\s+/)) {
        assert.ok(words(sheet.textContent!).includes(words(sentence)), `Missing approved instruction: ${sentence}`);
      }
      const dose = sheet.querySelector(".rehab-guide-dose")!.textContent!;
      assert.ok(dose.includes(`Sets${block.sets}`) && dose.includes(`Reps${block.reps}`));
      assert.match(sheet.textContent!, /Bodyweight only/);
      assert.match(sheet.textContent!, /Safety limits/);
      // Multi-sentence rules become one safety bullet per sentence, unchanged.
      for (const rule of block.stop_rules ?? []) assert.ok(words(sheet.textContent!).includes(words(rule)), `Missing stop rule: ${rule}`);
      assert.doesNotMatch(sheet.textContent!, /Stop if Once daily/);
      assert.doesNotMatch(sheet.textContent!, /mandatory_restrictions|automatic_increase/);
      assert.equal(sheet.querySelectorAll("form").length, 0);
    } finally { cleanup(); }
  });
}

for (const running of [false, true]) {
  test(`actual Today LOAD prescription and demo remain available with running=${running}`, async () => {
    const { sheet, cleanup } = await open(load, demo, running);
    try {
      assert.match(sheet.querySelector(".rehab-guide-dose")!.textContent!, /Reps10.*Sets1/);
      assert.match(sheet.textContent!, /stable support/i);
      assert.match(sheet.textContent!, /Bodyweight only/);
      assert.match(sheet.textContent!, /Floor level only/);
      assert.match(sheet.textContent!, /No speed, bouncing, hopping or automatic progression/);
      assert.match(sheet.textContent!, /does not provide training or contact clearance/);
      // The plan's shared player leads the guide, outside any disclosure.
      assert.ok(sheet.querySelector('.rehab-guide-demo .ex-demo'));
      assert.match(sheet.innerHTML, /AAAAAAAAAAA/);
      // Completion is still owned by Today, never a new clinical-clearance button.
      assert.doesNotMatch(sheet.textContent!, /Approve|Unlock/);
    } finally { cleanup(); }
  });
}

for (const media of [null, { ...demo, video_id: "invalid" }]) {
  test(`missing or invalid demo leaves approved self-paced instructions usable: ${media?.video_id ?? "missing"}`, async () => {
    const { sheet, cleanup } = await open(restore, media);
    try {
      assert.match(sheet.textContent!, /Go at your own pace/);
      assert.match(sheet.textContent!, /Avoid forced chest stretches/);
      assert.doesNotMatch(sheet.textContent!, /Demo not assigned|Demo video/);
      assert.match(sheet.textContent!, /How to perform/);
      assert.equal(sheet.querySelector("iframe, .ex-demo"), null);
      assert.equal(sheet.querySelector(".sp-block-stats"), null);
      assert.doesNotMatch(sheet.textContent!, /\b\d+ (sets?|reps?|seconds?|kg)\b|ResistanceBodyweight/);
    } finally { cleanup(); }
  });
}

for (const [pilot, fixture] of Object.entries(bankFixtures) as Array<[string, typeof fixtures.achilles]>) {
  test(`${pilot}: newly classified bank prescription uses the shared player without fabricated numbers`, async () => {
    const block: StructuredBlock = fixture.view.live_prescription.session.blocks[0];
    const { sheet, cleanup } = await open(block, null);
    try {
      assert.ok(sheet.textContent!.includes(block.display_name!));
      for (const equipment of block.drill_snapshot?.equipment ?? []) {
        assert.ok(sheet.textContent!.toLowerCase().includes(equipment.replaceAll("_", " ")));
      }
      if (Object.keys(block.dose ?? {}).length === 0) {
        assert.match(sheet.textContent!, /Self-paced/);
        assert.equal(sheet.querySelector(".sp-block-stats"), null);
      } else {
        assert.match(sheet.textContent!, /10 seconds/);
        assert.match(sheet.textContent!, /repeat 10 times/);
        assert.doesNotMatch(sheet.textContent!, /Self-paced/);
      }
      assert.doesNotMatch(sheet.textContent!, /Demo not assigned|Demo video/);
      assert.ok(sheet.querySelector(".rehab-guide-how ol li"));
      assert.equal(sheet.querySelectorAll("form").length, 0);
    } finally { cleanup(); }
  });
}
