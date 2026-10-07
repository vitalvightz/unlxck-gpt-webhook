import test from "node:test";
import assert from "node:assert/strict";

import {
  buildGuideScript,
  elapsedBefore,
  fightVisualisationFromSession,
  isFightVisualisationSession,
  type FightVisualisation,
} from "./script.ts";
import { pickVoice } from "./narrator.ts";
import type { StructuredSession } from "../types.ts";

// The shape the locked merge writes for a D-7 Fight Visualisation.
const d7Session: StructuredSession = {
  session_id: "locked-d-7-fight-visualization",
  session_type: "skill",
  title: "Fight Visualisation",
  objective: "Rehearse building and rebuilding your range against a fighter who wants to close it.",
  mindset_anchor: { confidence_anchor: "Score, move, see again." },
  blocks: [
    {
      block_type: "mindset",
      display_name: "Tactical Picture",
      duration: { value: 8, unit: "minutes" },
      purpose: "Rehearse building and rebuilding your range against a fighter who wants to close it.",
      coaching_cues: [
        "See the opponent starting to shorten the distance.",
        "Score on the way in with your trained lead, then move off line before they set.",
        "Rebuild your range immediately and see the picture clearly again.",
        "Run it again with them entering from the other side.",
        "Cue: Score, move, see again.",
      ],
    },
  ],
};

const d0: FightVisualisation = {
  name: "Trust → Compete",
  why: "Stop conscious over-analysis and hand the fight to your trained reactions.",
  steps: [
    "See the ring and feel your feet underneath you.",
    "See the opponent clearly. One breath.",
    "Bring up your fight cue.",
    "Read what is actually there and trust your reactions.",
  ],
  cue: "See it, trust it, go.",
  preBout: "Twenty seconds: one breath, feet under you, fight cue up, go.",
  durationSec: 3 * 60,
};

test("the locked Fight Visualisation session is recognised by title or id", () => {
  assert.equal(isFightVisualisationSession(d7Session), true);
  assert.equal(isFightVisualisationSession({ session_id: "locked-d-1-fight-visualization" }), true);
  assert.equal(isFightVisualisationSession({ title: "Tactical Focus" }), false);
  assert.equal(isFightVisualisationSession({ title: "Strength & Power" }), false);
});

test("bank instructions become steps; the cue and pre-bout lines are split out", () => {
  const visualisation = fightVisualisationFromSession(d7Session);
  assert.ok(visualisation);
  assert.equal(visualisation.name, "Tactical Picture");
  assert.equal(visualisation.steps.length, 4);
  assert.equal(visualisation.cue, "Score, move, see again.");
  assert.equal(visualisation.preBout, null);
  assert.equal(visualisation.durationSec, 480);

  const fightDay = fightVisualisationFromSession({
    ...d7Session,
    blocks: [
      {
        block_type: "mindset",
        display_name: "Trust → Compete",
        coaching_cues: [...d0.steps, "Cue: See it, trust it, go.", `Pre-bout: ${d0.preBout}`],
      },
    ],
  });
  assert.equal(fightDay?.preBout, d0.preBout);
  assert.equal(fightDay?.steps.length, 4);
});

test("a visualisation session with no steps has nothing to guide", () => {
  assert.equal(
    fightVisualisationFromSession({ ...d7Session, blocks: [{ block_type: "mindset", display_name: "Familiar & Ready" }] }),
    null,
  );
  assert.equal(fightVisualisationFromSession({ title: "Tactical Focus", blocks: d7Session.blocks }), null);
});

test("every bank line is spoken verbatim, in order", () => {
  const visualisation = fightVisualisationFromSession(d7Session)!;
  const spoken = buildGuideScript(visualisation)
    .segments.filter((item) => item.kind === "say")
    .map((item) => item.text)
    .join("\n");
  let cursor = 0;
  for (const step of visualisation.steps) {
    const at = spoken.indexOf(step, cursor);
    assert.ok(at >= cursor, `missing or out of order: ${step}`);
    cursor = at + step.length;
  }
  assert.match(spoken, /Your cue\. Score, move, see again\./);
});

test("every step is followed by silence for the athlete to run it", () => {
  const { segments } = buildGuideScript(fightVisualisationFromSession(d7Session)!);
  segments.forEach((item, index) => {
    if (item.kind === "say" && item.phase === "rehearse") {
      const next = segments[index + 1];
      assert.equal(next?.kind, "hold");
      assert.ok(next.kind === "hold" && next.seconds >= 5);
    }
  });
});

test("the guided run fits the prescribed dose", () => {
  for (const durationSec of [60, 180, 300, 480]) {
    const script = buildGuideScript({ ...d0, durationSec });
    // Short doses have a floor (settle + minimum gaps); longer ones land close.
    const ceiling = Math.max(durationSec * 1.1, 150);
    assert.ok(script.totalSec <= ceiling, `${durationSec}s dose ran ${script.totalSec}s`);
    if (durationSec >= 300) {
      assert.ok(script.totalSec >= durationSec * 0.8, `${durationSec}s dose ran only ${script.totalSec}s`);
    }
  }
});

test("long doses add a real-time run-through; fight day carries the pre-bout line", () => {
  const long = buildGuideScript({ ...d0, durationSec: 480 }).segments;
  assert.ok(long.some((item) => item.kind === "say" && /run it all again/i.test(item.text)));
  const short = buildGuideScript(d0).segments;
  assert.ok(!short.some((item) => item.kind === "say" && /run it all again/i.test(item.text)));
  assert.ok(short.some((item) => item.kind === "say" && item.text.includes("Twenty seconds")));
  assert.equal(short.at(-2)?.kind, "say");
  assert.equal(short.at(-2)?.kind === "say" && short.at(-2)?.phase, "close");
});

test("elapsed time is the sum of the segments before an index", () => {
  const script = buildGuideScript(d0);
  assert.equal(elapsedBefore(script, 0), 0);
  assert.equal(Math.round(elapsedBefore(script, script.segments.length)), script.totalSec);
});

test("the narrator prefers a natural English voice", () => {
  const voice = (name: string, lang: string, localService = true) =>
    ({ name, lang, localService }) as SpeechSynthesisVoice;
  assert.equal(
    pickVoice([voice("Thomas", "fr-FR"), voice("Fred", "en-US"), voice("Daniel (Enhanced)", "en-GB")])?.name,
    "Daniel (Enhanced)",
  );
  assert.equal(pickVoice([voice("Fred", "en-US")])?.name, "Fred");
  assert.equal(pickVoice([voice("Thomas", "fr-FR")]), null);
});
