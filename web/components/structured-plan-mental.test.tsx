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
      assert.match(html, new RegExp(`${title} · 5 min`));
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
