import test from "node:test";
import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";

import { ExerciseMediaProvider } from "./exercise-demo";
import { ExerciseRow, SessionCard } from "./structured-plan-renderer";
import type { ExerciseMedia, StructuredBlock, StructuredSession } from "@/lib/types";

function countOccurrences(text: string, needle: string): number {
  return text.split(needle).length - 1;
}

const rdl: StructuredBlock = {
  block_id: "rdl",
  block_type: "strength",
  display_name: "Romanian Deadlift (RDL)",
  sets: 3,
  reps: "8-12",
  effort: { method: "RPE", value: 7 },
  purpose: "Build posterior chain strength with controlled eccentrics.",
  why_today: "Maintain lower-body force without heavy soreness.",
  coaching_cues: ["Hinge at the hips and keep the bar close to legs.", "Lower on a 3-1-1 tempo."],
};

const sled: StructuredBlock = {
  block_id: "sled",
  block_type: "strength",
  display_name: "Sled Push",
  sets: 3,
  purpose: "Build leg drive.",
  why_today: "Build leg drive.",
  coaching_cues: ["Short powerful steps."],
  stop_rules: ["Stop when steps shorten or hips rise."],
};

const session = {
  session_id: "lower",
  session_type: "strength_power",
  title: "Lower-body strength",
  blocks: [rdl, sled],
} satisfies StructuredSession;

const coachDemo: ExerciseMedia = {
  provider: "youtube",
  video_id: "dQw4w9WgXcQ",
  start_s: 42,
  end_s: 70,
  source: "coach",
  channel_title: "UNLXCK Coaching",
};

test("session renders every exercise as a row with only the first one open", () => {
  const html = renderToStaticMarkup(<SessionCard session={session} defaultOpenBlocks />);

  assert.equal(countOccurrences(html, 'class="ex-row"'), 2);
  assert.equal(countOccurrences(html, 'aria-expanded="true"'), 2); // session toggle + first row
  assert.equal(html.includes("Romanian Deadlift (RDL)"), true);
  assert.equal(html.includes("Sled Push"), true);
  // Row header stat line uses the same reconciled prescription as the card.
  assert.equal(html.includes("3 × 8-12 · RPE 7"), true);
  // First row is open: its reasons show; the second row's cues stay behind the tap.
  assert.equal(html.includes("Build posterior chain strength with controlled eccentrics."), true);
  assert.equal(html.includes("Short powerful steps."), false);
});

test("a collapsed row still shows its stop rule, and an open row shows it exactly once", () => {
  const collapsed = renderToStaticMarkup(<ExerciseRow block={sled} open={false} onToggle={() => {}} />);
  assert.equal(countOccurrences(collapsed, "Stop when steps shorten or hips rise."), 1);
  assert.equal(countOccurrences(collapsed, ">Stop rule</span>"), 1);

  const open = renderToStaticMarkup(<ExerciseRow block={sled} open onToggle={() => {}} />);
  assert.equal(countOccurrences(open, "Stop when steps shorten or hips rise."), 1);
});

test("open row names what the exercise builds and why it is in today's session", () => {
  const html = renderToStaticMarkup(<ExerciseRow block={rdl} open onToggle={() => {}} />);

  assert.equal(html.includes(">Builds</span>Build posterior chain strength"), true);
  assert.equal(html.includes(">Why today</span>Maintain lower-body force"), true);
});

test("a why-today line that repeats the purpose is printed once", () => {
  const html = renderToStaticMarkup(<ExerciseRow block={sled} open onToggle={() => {}} />);

  assert.equal(countOccurrences(html, "Build leg drive."), 1);
  assert.equal(html.includes(">Why today</span>"), false);
});

test("without media an exercise is cues-only: no player, no broken frame", () => {
  const html = renderToStaticMarkup(<ExerciseRow block={rdl} open onToggle={() => {}} />);

  assert.equal(html.includes("ex-demo"), false);
  assert.equal(html.includes("ytimg"), false);
  assert.equal(html.includes("Hinge at the hips and keep the bar close to legs."), true);
});

test("with media the open row leads with a tap-to-play demo and pins the key cue once", () => {
  const html = renderToStaticMarkup(
    <ExerciseMediaProvider media={{ "Romanian Deadlift (RDL)": coachDemo }}>
      <ExerciseRow block={rdl} open onToggle={() => {}} />
    </ExerciseMediaProvider>,
  );

  // Facade only: no iframe or player script until the athlete taps.
  assert.equal(html.includes("<iframe"), false);
  assert.equal(html.includes('aria-label="Play Romanian Deadlift (RDL) demo"'), true);
  assert.equal(html.includes("https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg"), true);
  assert.equal(html.includes("Demo · 0:42–1:10 · UNLXCK Coaching"), true);
  // Nothing is layered over the frame: the badge and labels sit under it, and
  // the full video on YouTube is linked before anything plays.
  const frame = html.slice(html.indexOf('class="ex-demo-frame"'), html.indexOf('class="ex-demo-caption"'));
  assert.ok(frame.length > 0);
  assert.equal(frame.includes("Coach demo"), false);
  assert.equal(frame.includes("Demo ·"), false);
  const caption = html.slice(html.indexOf('class="ex-demo-caption"'));
  assert.equal(caption.includes(">Coach demo</span>"), true);
  assert.equal(caption.includes('href="https://www.youtube.com/watch?v=dQw4w9WgXcQ&amp;t=42s"'), true);
  assert.equal(caption.includes(">Watch on YouTube</a>"), true);
  // Key cue sits under the video and is not repeated in the cue list.
  assert.equal(html.includes(">Key cue</span>"), true);
  assert.equal(countOccurrences(html, "Hinge at the hips and keep the bar close to legs."), 1);
  assert.equal(html.includes("Lower on a 3-1-1 tempo."), true);
});

test("collapsed row with media shows a thumbnail and tells screen readers there is a demo", () => {
  const html = renderToStaticMarkup(
    <ExerciseMediaProvider media={{ "Romanian Deadlift (RDL)": { ...coachDemo, source: "curated" } }}>
      <ExerciseRow block={rdl} open={false} onToggle={() => {}} />
    </ExerciseMediaProvider>,
  );

  assert.equal(html.includes("https://i.ytimg.com/vi/dQw4w9WgXcQ/mqdefault.jpg"), true);
  assert.equal(html.includes("Has demo video."), true);
  assert.equal(html.includes("Coach demo"), false);
});

test("media is matched on the exact display name only", () => {
  const html = renderToStaticMarkup(
    <ExerciseMediaProvider media={{ "Sled Push": coachDemo }}>
      <ExerciseRow block={rdl} open onToggle={() => {}} />
    </ExerciseMediaProvider>,
  );

  assert.equal(html.includes("ex-demo"), false);
});
