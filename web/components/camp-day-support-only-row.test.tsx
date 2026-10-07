import test from "node:test";
import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";

import { CampDayCard } from "./structured-plan-renderer";
import type { StructuredDay } from "@/lib/types";

const mindset = { intent: "", focus_cue: "", reset_cue: "" };

function day(sessions: StructuredDay["sessions"]): StructuredDay {
  return {
    date: "2026-10-29",
    countdown_label: "D-3",
    day_type: "low",
    phase_label: "TAPER",
    today_card: { headline: "", readiness_status: "train_as_planned", mindset_anchor: mindset },
    sessions,
  } as StructuredDay;
}

const visualisation = {
  session_id: "locked-d-3-fight-visualization",
  session_type: "skill",
  title: "Fight Visualisation",
  objective: "See the opening exchanges.",
  mindset_anchor: mindset,
  blocks: [{ block_type: "mindset", display_name: "Familiar & Ready" }],
};

const skipFlush = {
  session_id: "ses-skip",
  session_type: "conditioning",
  title: "Light Skipping Flush",
  objective: "Keep rhythm.",
  mindset_anchor: mindset,
  blocks: [{ block_type: "conditioning", display_name: "Light Skipping Flush" }],
};

test("a support-only day names itself instead of leaving the count slot blank", () => {
  // Production D-3: only a Fight Visualisation. Physical counts exclude
  // zero-load support, so the row used to show neither a count nor a label.
  const html = renderToStaticMarkup(
    <CampDayCard day={day([visualisation] as StructuredDay["sessions"])} />,
  );

  assert.match(html, /cm-day-support[^>]*>Zero load/);
  assert.doesNotMatch(html, /\d+\/\d+/);
});

test("a day with physical work keeps its count and no support label", () => {
  const html = renderToStaticMarkup(
    <CampDayCard day={day([visualisation, skipFlush] as StructuredDay["sessions"])} />,
  );

  assert.match(html, /0\/1/);
  assert.doesNotMatch(html, /cm-day-support/);
});
