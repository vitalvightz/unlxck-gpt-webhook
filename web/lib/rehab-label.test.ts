import test from "node:test";
import assert from "node:assert/strict";

import {
  isRehabBlock,
  normalizeRehabText,
  resolveBlockRehabLabel,
  resolveRehabSummaryLabel,
} from "@/lib/rehab-label";
import type { RehabLabelPolicy, StructuredBlock } from "@/lib/types";

const HAMSTRING_BLOCK: StructuredBlock = {
  block_id: "isometric-hamstring-bridge-hold",
  block_type: "rehab",
  display_name: "Isometric Hamstring Bridge Hold",
};

const GROIN_BLOCK: StructuredBlock = {
  block_id: "copenhagen-plank",
  block_type: "rehab",
  display_name: "Copenhagen Plank",
};

const hamstringOpen: RehabLabelPolicy = {
  default_mode: "prehab",
  active_regions: [{ region: "hamstring", terms: ["hamstring", "hamstrings", "back of thigh"] }],
};

const quadOpen: RehabLabelPolicy = {
  default_mode: "prehab",
  active_regions: [{ region: "quads", terms: ["quad", "quads", "quadriceps"] }],
};

test("normalizeRehabText drops parentheticals and collapses punctuation", () => {
  assert.equal(normalizeRehabText("Isometric Hamstring Bridge Hold (30s)"), "isometric hamstring bridge hold");
  assert.equal(normalizeRehabText("Single-Leg RDL — 3x8"), "single leg rdl 3x8");
  assert.equal(normalizeRehabText(null), "");
});

test("isRehabBlock only matches the rehab block type", () => {
  assert.equal(isRehabBlock(HAMSTRING_BLOCK), true);
  assert.equal(isRehabBlock({ block_type: "REHAB" }), true);
  assert.equal(isRehabBlock({ block_type: "mobility" }), false);
  assert.equal(isRehabBlock({}), false);
});

test("a rehab block whose region is still injured reads Rehab", () => {
  assert.equal(resolveBlockRehabLabel(HAMSTRING_BLOCK, hamstringOpen), "Rehab");
});

test("a cleared region reads Prehab even while another region is injured", () => {
  // The bug: one open quad flag pinned every rehab block to "Rehab", so cleared
  // hamstring work kept reading Rehab.
  assert.equal(resolveBlockRehabLabel(HAMSTRING_BLOCK, quadOpen), "Prehab");
});

test("no live injuries at all reads Prehab", () => {
  assert.equal(
    resolveBlockRehabLabel(HAMSTRING_BLOCK, { default_mode: "prehab", active_regions: [] }),
    "Prehab",
  );
});

test("an unlocalizable live injury holds every block on Rehab", () => {
  assert.equal(
    resolveBlockRehabLabel(HAMSTRING_BLOCK, { default_mode: "rehab", active_regions: [] }),
    "Rehab",
  );
});

test("a missing policy keeps the unchanged Rehab wording", () => {
  assert.equal(resolveBlockRehabLabel(HAMSTRING_BLOCK, null), "Rehab");
  assert.equal(resolveBlockRehabLabel(HAMSTRING_BLOCK, undefined), "Rehab");
});

test("purpose and cues can supply the region the drill name omits", () => {
  const block: StructuredBlock = {
    block_type: "rehab",
    display_name: "Nordic Curl Eccentrics",
    purpose: "Targets hamstring strain during GPP phase.",
  };
  assert.equal(resolveBlockRehabLabel(block, hamstringOpen), "Rehab");
  assert.equal(resolveBlockRehabLabel(block, quadOpen), "Prehab");
});

test("bank drill terms catch blocks that never name their region", () => {
  // "Copenhagen Plank" says nothing about the groin; the server ships the drill
  // name as a term so live groin rehab is not downgraded to Prehab.
  const groinOpen: RehabLabelPolicy = {
    default_mode: "prehab",
    active_regions: [{ region: "groin", terms: ["groin", "adductors", "copenhagen plank"] }],
  };
  assert.equal(resolveBlockRehabLabel(GROIN_BLOCK, groinOpen), "Rehab");
  assert.equal(resolveBlockRehabLabel(GROIN_BLOCK, quadOpen), "Prehab");
});

test("terms match whole words, not fragments", () => {
  const hipOpen: RehabLabelPolicy = {
    default_mode: "prehab",
    active_regions: [{ region: "hip", terms: ["hip"] }],
  };
  const block: StructuredBlock = { block_type: "rehab", display_name: "Ship Rope Waves" };
  assert.equal(resolveBlockRehabLabel(block, hipOpen), "Prehab");
});

test("a mixed session summary stays Rehab while any one block is live", () => {
  assert.equal(resolveRehabSummaryLabel([HAMSTRING_BLOCK, GROIN_BLOCK], hamstringOpen), "Rehab");
  assert.equal(resolveRehabSummaryLabel([HAMSTRING_BLOCK, GROIN_BLOCK], quadOpen), "Prehab");
});

test("a mobility-only summary keeps the standing Rehab wording", () => {
  // The summary list also carries mobility blocks. With no rehab work in the
  // session there is nothing to have cleared, so the heading must not flip.
  const mobility: StructuredBlock = { block_type: "mobility", display_name: "Hip Airplanes" };
  assert.equal(resolveRehabSummaryLabel([mobility], quadOpen), "Rehab");
  assert.equal(resolveRehabSummaryLabel([], quadOpen), "Rehab");
});
