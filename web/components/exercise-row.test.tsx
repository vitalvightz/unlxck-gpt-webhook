import test from "node:test";
import assert from "node:assert/strict";
import type React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { ExerciseMediaProvider } from "./exercise-demo";
import { ExerciseRationaleProvider, ExerciseRow, SessionCard } from "./structured-plan-renderer";
import type { ExerciseMedia, StructuredBlock, StructuredSession } from "@/lib/types";

function countOccurrences(text: string, needle: string): number {
  return text.split(needle).length - 1;
}

/** The header metadata line of one row as plain text ("STRENGTH" excluded). */
function summaryText(html: string, title: string): string {
  const row = html.slice(html.indexOf(`>${title}</span>`));
  const summary = row.slice(row.indexOf('class="ex-row-summary"'));
  const end = summary.indexOf("</span></span></span>");
  return summary
    .slice(summary.indexOf(">") + 1, end)
    .replace(/<[^>]+>/g, "")
    .trim();
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

/** Renders as the Today screen does, where "Builds" / "Why today" are shown. */
function onToday(node: React.ReactNode): string {
  return renderToStaticMarkup(<ExerciseRationaleProvider>{node}</ExerciseRationaleProvider>);
}

test("session renders every exercise as a row with only the first one open", () => {
  const html = onToday(<SessionCard session={session} defaultOpenBlocks />);

  assert.equal(countOccurrences(html, 'class="ex-row"'), 2);
  assert.equal(countOccurrences(html, 'aria-expanded="true"'), 2); // session toggle + first row
  assert.equal(html.includes("Romanian Deadlift (RDL)"), true);
  assert.equal(html.includes("Sled Push"), true);
  // Row header stat line uses the same reconciled prescription as the card.
  assert.equal(summaryText(html, "Romanian Deadlift (RDL)"), "3 × 8-12 · RPE 7");
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
  const html = onToday(<ExerciseRow block={rdl} open onToggle={() => {}} />);

  assert.equal(html.includes(">Builds</span>Build posterior chain strength"), true);
  assert.equal(html.includes(">Why today</span>Maintain lower-body force"), true);
});

test("a why-today line that repeats the purpose is printed once", () => {
  const html = onToday(<ExerciseRow block={sled} open onToggle={() => {}} />);

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

test("only a portrait video marks the demo; landscape and undetected render the same markup", () => {
  const render = (orientation?: ExerciseMedia["orientation"]) =>
    renderToStaticMarkup(
      <ExerciseMediaProvider
        media={{ "Romanian Deadlift (RDL)": orientation === undefined ? coachDemo : { ...coachDemo, orientation } }}
      >
        <ExerciseRow block={rdl} open onToggle={() => {}} />
      </ExerciseMediaProvider>,
    );

  const legacy = render();
  assert.equal(legacy.includes("data-orientation"), false);
  // Null (not detected yet) and landscape are byte-identical to a payload
  // that predates the field: the 16:9 layout is the fallback, not a variant.
  assert.equal(render(null), legacy);
  assert.equal(render("landscape"), legacy);

  const portrait = render("portrait");
  assert.equal(portrait.includes('class="ex-demo" data-mode="facade" data-orientation="portrait"'), true);
  // Same player, clip and caption: only the frame's shape is flagged.
  assert.equal(portrait.replace(' data-orientation="portrait"', ""), legacy);
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

const rehabCurl: StructuredBlock = {
  block_id: "curl",
  block_type: "rehab",
  display_name: "Suspension Curl (control drill)",
  sets: 2,
  reps: "8",
  load: { method: "other", value: 0, unit: "other", display: "easy angle" },
  rest: { value: 90, unit: "seconds" },
  effort: { method: "RPE", value: 6 },
  regression_options: ["Use a lighter band."],
  stop_rules: ["Sharp pain during the pull"],
};

const bagRounds: StructuredBlock = {
  block_id: "bag",
  block_type: "conditioning",
  display_name: "Heavy-bag technical rounds",
  duration: { value: 2, unit: "minutes" },
  rounds: 3,
  work: { value: 120, unit: "seconds" },
  rest: { value: 180, unit: "seconds" },
  effort: { method: "RPE", value: 4 },
  stop_rules: ["Heavy breathing"],
};

test("the exercise type leads the header line, with its glossary, and leaves the card body", () => {
  const html = renderToStaticMarkup(<ExerciseRow block={rehabCurl} open onToggle={() => {}} />);

  const meta = html.slice(html.indexOf('class="ex-row-meta"'), html.indexOf('class="ex-row-body"'));
  assert.equal(meta.includes('class="ex-row-type">Rehab'), true);
  // Rehab keeps its definition: the "i" sits beside the type in the header.
  assert.equal(meta.includes('aria-label="What Rehab means"'), true);
  // No pill left floating inside the open card.
  assert.equal(html.includes('class="sp-tag"'), false);
  assert.equal(html.includes('class="sp-block-head"'), false);
});

test("the header toggle is the only button around the title, never wrapping another control", () => {
  const html = renderToStaticMarkup(<ExerciseRow block={rehabCurl} open onToggle={() => {}} />);

  const toggle = html.slice(html.indexOf('class="ex-row-toggle"'));
  const toggleBody = toggle.slice(0, toggle.indexOf("</button>"));
  assert.equal(toggleBody.includes("<button"), false);
  assert.equal(toggleBody.includes("Suspension Curl (control drill)"), true);
  assert.equal(countOccurrences(html, 'aria-expanded="true"'), 1);
});

test("the prescription panel knows its field count and prints times short", () => {
  const html = renderToStaticMarkup(<ExerciseRow block={bagRounds} open onToggle={() => {}} />);

  assert.equal(html.includes('class="sp-block-stats" data-count="5"'), true);
  assert.equal(html.includes(">Work</span></span>2 min</span>"), true);
  assert.equal(html.includes(">Rest</span>3 min</span>"), true);
  assert.equal(html.includes("seconds"), false);
  // The header line agrees with the panel.
  assert.equal(summaryText(html, "Heavy-bag technical rounds"), "2 min · RPE 4");
});

test("adjustments close the card as one group, with the stop rule marked", () => {
  const html = renderToStaticMarkup(<ExerciseRow block={rehabCurl} open onToggle={() => {}} />);

  const group = html.slice(html.indexOf('class="sp-block-asides"'));
  assert.equal(group.includes(">Easier</span>Use a lighter band."), true);
  assert.equal(group.includes('data-kind="stop"'), true);
  assert.equal(countOccurrences(html, "Sharp pain during the pull"), 1);
});

test("a demo thumbnail shows on the collapsed row only; rows without a demo have no tile", () => {
  const media = { "Romanian Deadlift (RDL)": coachDemo };
  const collapsed = renderToStaticMarkup(
    <ExerciseMediaProvider media={media}>
      <ExerciseRow block={rdl} open={false} onToggle={() => {}} />
    </ExerciseMediaProvider>,
  );
  const open = renderToStaticMarkup(
    <ExerciseMediaProvider media={media}>
      <ExerciseRow block={rdl} open onToggle={() => {}} />
    </ExerciseMediaProvider>,
  );
  const noDemo = renderToStaticMarkup(<ExerciseRow block={sled} open={false} onToggle={() => {}} />);

  assert.equal(countOccurrences(collapsed, 'class="ex-row-thumb"'), 1);
  assert.equal(open.includes('class="ex-row-thumb"'), false);
  assert.equal(noDemo.includes("ex-row-thumb"), false);
});

test("the plan view leaves out Builds and Why today; only Today shows them", () => {
  const plan = renderToStaticMarkup(<SessionCard session={session} defaultOpenBlocks />);

  assert.equal(plan.includes(">Builds</span>"), false);
  assert.equal(plan.includes(">Why today</span>"), false);
  assert.equal(plan.includes("Build posterior chain strength"), false);
  // The prescription itself is unchanged.
  assert.equal(plan.includes('class="sp-block-stats"'), true);

  const today = onToday(<SessionCard session={session} defaultOpenBlocks />);
  assert.equal(today.includes(">Builds</span>Build posterior chain strength"), true);
});

test("a lower-case load reads sentence-case in the panel and the header", () => {
  const hold: StructuredBlock = {
    block_id: "hold",
    block_type: "strength",
    display_name: "Staggered Stance Hold",
    load: { method: "bodyweight", value: 0, unit: "bodyweight", display: "bodyweight" },
    rest: { value: 60, unit: "seconds" },
    effort: { method: "RPE", value: 4 },
  };
  const html = renderToStaticMarkup(<ExerciseRow block={hold} open onToggle={() => {}} />);

  assert.equal(html.includes("</span></span>Bodyweight</span>"), true);
  assert.equal(summaryText(html, "Staggered Stance Hold"), "Bodyweight · RPE 4");
  assert.equal(html.includes("bodyweight"), false);
});
