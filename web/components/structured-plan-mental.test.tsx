import test from "node:test";
import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";
import { SessionCard } from "./structured-plan-renderer";
import { mentalSessionCategory, mentalSessionSummary, mentalTaskSteps } from "../lib/structured-plan";
import type { StructuredSession } from "../lib/types";

for (const [title, category] of [["Fight Visualisation", "Visualise"], ["Neural Visualisation", "Visualise"],
  ["Tactical Watch", "Analyse"], ["Tactical Focus", "Analyse"], ["Self-Review Cues", "Reflect"]]) {
  test(`${title} shows instructions without dropdowns in both layouts`, () => {
    const session: StructuredSession = { session_id: `saved-${title}`, title, session_type: "skill",
      planned_duration: { value: 5, unit: "minutes" }, objective: "Original selected scenario instruction.",
      blocks: [{ block_id: "original-block", display_name: title, coaching_cues: ["Keep the original bank cue."],
        duration: { value: 5, unit: "minutes" } }] };
    assert.equal(mentalSessionCategory(session), category);
    for (const layout of ["card", "section"] as const) {
      const html = renderToStaticMarkup(<SessionCard session={session} layout={layout} defaultOpenBlocks
        completionInfo={{ onLog: () => {}, display: { state: "done", label: "Done", tone: "green" } }} />);
      if (category === "Analyse" || category === "Reflect") {
        assert.match(html, new RegExp(title));
        assert.doesNotMatch(html, new RegExp(`${title} · 5 min`));
      } else {
        assert.match(html, new RegExp(`${title} · 5 min`));
      }
      assert.doesNotMatch(html, /<details/);
      assert.doesNotMatch(html, /<details[^>]* open/);

      assert.match(html, /Keep the original bank cue/);
      assert.match(html, /Log this session/);
      assert.doesNotMatch(html, /Zero load/);
    }
  });
}

test("physical coaching and passive resets keep their normal presentation", () => {
  for (const title of ["Breathing Reset", "Strength", "Hard sparring"]) {
    assert.equal(mentalSessionCategory({ title, session_type: "strength_power" }), null);
  }
  assert.equal(mentalSessionCategory({ title: "Strength", session_type: "strength_power",
    blocks: [{ display_name: "Neural Visualisation" }] }), null);
});


test("compact mental card keeps completion callback and selected instruction", async () => {
  await import("./test-dom");
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  let logged = 0;
  try {
    await act(async () => root.render(<SessionCard session={{ session_id: "existing-review", title: "Self-Review Cues",
      objective: "Keep the coach's existing instruction.", session_type: "skill" }}
      completionInfo={{ display: { state: "pending", tone: "neutral", label: "" }, onLog: () => logged++ }} />));
    const button = Array.from(host.querySelectorAll("button")).find(button => button.textContent === "Log this session");
    assert.ok(button);
    await act(async () => button.click());
    assert.equal(logged, 1);
    assert.match(host.textContent ?? "", /Keep the coach's existing instruction/);
  } finally {
    await act(async () => root.unmount());
    host.remove();
  }
});


test("a legacy mental title cannot hide bundled physical exercises", () => {
  assert.equal(mentalSessionCategory({ title: "Fight Visualisation", session_type: "skill",
    blocks: [{ block_type: "mindset", display_name: "Quiet rehearsal" },
      { block_type: "preparation", display_name: "Hip CARs" }] }), null);
});

test("all mental actions survive in order, including the middle decision", () => {
  assert.deepEqual(mentalTaskSteps([
    "5 minutes, RPE 1.", "Step 1: Find safe scoring range.",
    "Step 2: Find their danger range.", "Step 3: Choose a strike.",
    "Step 4: Write one rule to test.", "Focus: Stay calm.", "Progress: Test it later.",
  ]), ["Find safe scoring range.", "Find their danger range.", "Choose a strike.", "Write one rule to test."]);
});

test("the rendered visualisation retains the response branch and reset", () => {
  const html = renderToStaticMarkup(<SessionCard session={{ title: "Fight Visualisation", session_type: "mindset",
    blocks: [{ block_type: "mindset", display_name: "Tactical Picture", coaching_cues: [
      "Step 1: See the opponent commit to an entry.",
      "Step 2: Read whether the head stays high or drops before you answer.",
      "Step 3: Counter the high entry; meet the low entry with your frame and hips.",
      "Step 4: Reset your stance and run both versions again.",
    ] }] }} />);
  assert.match(html, /Counter the high entry; meet the low entry with your frame and hips/);
  assert.match(html, /Reset your stance and run both versions again/);
  assert.equal((html.match(/<li(?: |>)/g) ?? []).length, 4);
});

test("mental preview uses selected authored instructions and keeps smart truncation lossless in details", () => {
  const first = { title: "Fight Visualisation", blocks: [{ coaching_cues: ["Enter behind your jab and cut off the exit."] }] };
  const second = { title: "Fight Visualisation", blocks: [{ coaching_cues: ["Draw the entry and counter as they reset."] }] };
  assert.equal(mentalSessionSummary(first), "Enter behind your jab and cut off the exit.");
  assert.notEqual(mentalSessionSummary(first), mentalSessionSummary(second));
  assert.equal(mentalSessionSummary({ blocks: [{ coaching_cues: ["2 minutes, RPE 1 max.", "Review the last clean technical work."] }] }), "Review the last clean technical work.");
  const long = "Keep the exit in view. " + "Follow the selected authored instruction without changing it. ".repeat(5);
  assert.equal(mentalSessionSummary({ blocks: [{ coaching_cues: [long] }] }), "Keep the exit in view.");
  assert.ok((mentalSessionSummary({ objective: "Move through the familiar sequence ".repeat(12) })?.length ?? 0) <= 180);
});


test("mental safety remains visible outside disclosures", () => {
  const html = renderToStaticMarkup(<SessionCard session={{title:"Fight Visualisation", session_type:"mindset",
    blocks:[{block_type:"mindset", display_name:"Calm rehearsal", coaching_cues:["Picture a familiar exchange."],
      stop_rules:["Stop if distress increases."]}]}}/>);
  assert.match(html, /Stop if distress increases/);
  assert.doesNotMatch(html, /<details/);
});

test("old D-40 mixed Tactical Picture gets mental layout", () => {
  const session = {
    title: "Fight Visualisation", session_type: "mixed",
    blocks: [{ block_type: "skill", display_name: "Tactical Picture",
      coaching_cues: ["Visualise them giving ground.", "Take space without chasing.",
        "Cut their exit.", "Rehearse them changing direction."] }],
  } as StructuredSession;
  assert.equal(mentalSessionCategory(session), "Visualise");
  const html = renderToStaticMarkup(<SessionCard session={session} />);
  assert.match(html, /sp-mental-steps/);
  assert.doesNotMatch(html, /Show less/);
});


for (const title of ["Fight Visualisation", "Self-Review Cues", "Tactical Watch", "Breathing Reset"]) {
  test(`Plan collapses ${title} and trusts only the server optional flag`, () => {
    for (const optional of [true, false, undefined]) {
      const session: StructuredSession = { title, session_type: title === "Breathing Reset" ? "recovery" : "mindset",
        optional, objective: "Optional. Preserve this authored description.",
        blocks: [{ block_id: "support", block_type: "mindset", display_name: title,
          coaching_cues: ["Step 1: Keep the first instruction.", "Step 2: Keep the second instruction."] }] };
      const html = renderToStaticMarkup(<SessionCard session={session} layout="plan" defaultOpenBlocks />);
      assert.match(html, /sp-session-support/);
      assert.match(html, /<details class="sp-optional-disclosure">/);
      assert.doesNotMatch(html, /<details[^>]* open/);
      assert.equal(html.includes("<span>Optional</span>"), optional === true);
      assert.doesNotMatch(html, /Optional\./);
      assert.match(html, /Preserve this authored description/);
      assert.match(html, /Keep the first instruction/);
      assert.match(html, /Keep the second instruction/);
      for (const layout of ["section", "card"] as const) {
        const today = renderToStaticMarkup(<SessionCard session={session} layout={layout} initiallyOpenFirstBlock={false} />);
        assert.doesNotMatch(today, /sp-session-support|sp-optional-disclosure/);
        if (title === "Breathing Reset") assert.match(today, /Optional\./);
      }
    }
  });
}

test("primary Plan sessions keep their presentation even when prose says Optional", () => {
  for (const session_type of ["strength_power", "conditioning", "skill", "sparring"]) {
    const html = renderToStaticMarkup(<SessionCard layout="plan" session={{ title: "Primary training", session_type,
      objective: "Optional. This is authored prose." }} />);
    assert.doesNotMatch(html, /sp-session-support|sp-optional-disclosure/);
  }
});

test("Plan support disclosure opens, closes, and retains logging", async () => {
  await import("./test-dom");
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  let logged = 0;
  try {
    await act(async () => root.render(<SessionCard layout="plan" defaultOpenBlocks session={{ title: "Self-Review Cues",
      session_type: "mindset", optional: true, objective: "Keep this description.",
      blocks: [{ block_type: "mindset", coaching_cues: ["Step 1: Keep this numbered instruction."] }] }}
      completionInfo={{ display: { state: "done", tone: "green", label: "Done" }, onLog: () => logged++ }} />));
    const details = host.querySelector("details.sp-optional-disclosure")! as HTMLDetailsElement;
    const summary = details.querySelector("summary")!;
    assert.equal(details.open, false);
    await act(async () => summary.click());
    assert.equal(details.open, true);
    assert.match(details.textContent ?? "", /Keep this numbered instruction/);
    assert.match(details.textContent ?? "", /Done/);
    const log = Array.from(details.querySelectorAll("button")).find(button => button.textContent === "Log this session")!;
    await act(async () => log.click());
    assert.equal(logged, 1);
    await act(async () => summary.click());
    assert.equal(details.open, false);
  } finally {
    await act(async () => root.unmount());
    host.remove();
  }
});


test("server optional sessions collapse without an Optional prose prefix", () => {
  const html = renderToStaticMarkup(<SessionCard layout="plan" session={{ title: "Fight Visualisation",
    session_type: "mindset", optional: true, objective: "Rehearse the opening exchange." }} />);
  assert.match(html, /sp-session-support/);
  assert.match(html, /<span>Optional<\/span>/);
  assert.match(html, /Rehearse the opening exchange/);
});


test("Plan never collapses protocols, bundled movement, or safety instructions", () => {
  const sessions: StructuredSession[] = [
    { title: "Fight-day protocol", session_type: "protocol" },
    { title: "Fight Visualisation", session_type: "protocol" },
    { title: "Fight Visualisation", session_type: "conditioning" },
    { title: "Fight Visualisation", session_type: "skill", blocks: [{block_type: "preparation", display_name: "Hip CARs"}] },
    { title: "Breathing Reset", session_type: "recovery", blocks: [{block_type: "preparation", display_name: "Walk flush"}] },
    { title: "Fight Visualisation", session_type: "mindset", blocks: [{block_type: "mindset", stop_rules: ["Stop if dizzy."]}] },
  ];
  for (const session of sessions) {
    const html = renderToStaticMarkup(<SessionCard layout="plan" session={session} initiallyOpenFirstBlock={false} />);
    assert.doesNotMatch(html, /sp-session-support|sp-optional-disclosure/);
  }
  const warning = renderToStaticMarkup(<SessionCard layout="plan" session={{title: "Breathing Reset", session_type: "recovery"}}
    day={{today_card: {primary_warning: "Important safety instruction."}}} />);
  assert.doesNotMatch(warning, /sp-optional-disclosure/);
  assert.match(warning, /Important safety instruction/);
});


test("Plan names a single matching exercise once while Today keeps its heading", () => {
  const session: StructuredSession = { title: "Joint Prep", session_type: "mobility", blocks: [
    { block_id: "prep", block_type: "preparation", display_name: "Joint Prep", duration: { value: 8, unit: "minutes" } }] };
  const html = renderToStaticMarkup(<SessionCard layout="plan" session={session} initiallyOpenFirstBlock={false} />);
  assert.equal((html.match(/>Joint Prep</g) || []).length, 1);
  const today = renderToStaticMarkup(<SessionCard layout="section" session={session} initiallyOpenFirstBlock={false} />);
  assert.match(today, /<h3[^>]*>Joint Prep<\/h3>/);
});
