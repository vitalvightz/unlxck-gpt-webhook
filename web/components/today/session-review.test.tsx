import test from "node:test";
import assert from "node:assert/strict";
import "../test-dom";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { SessionReview } from "./session-review";
import type { StructuredSession } from "@/lib/types";

test("review locks the entire save, including the batch write, and releases after failure", async () => {
  const root = createRoot(document.createElement("div"));
  const sessions: StructuredSession[] = [{ session_id: "s1", title: "Strength", blocks: [
    { block_id: "b1", block_type: "strength", display_name: "Deadlift", sets: 3, reps: 5 },
  ] }];
  let writes = 0;
  let completions = 0;
  let rejectWrite: (error: Error) => void = () => {};
  try {
    await act(async () => { root.render(<SessionReview title="Review" sessions={sessions}
      logging={{logs: {}, painReasonAllowed: false, save: async () => {}, saveMany: () => {
        writes++;
        return new Promise<void>((_, reject) => { rejectWrite = reject; });
      }}} blocks={<p>Deadlift</p>} hint="Review" canCollectPain={false} isSubmitting={false}
      onClose={() => { throw new Error("Cannot close during a write"); }}
      onSave={async () => { completions++; return true; }} />); });
    const save = Array.from(document.querySelectorAll("button")).find(button => button.textContent === "Save as skipped")!;
    assert.ok(save);
    await act(async () => { save.click(); save.click(); });
    assert.equal(writes, 1);
    assert.equal(save.disabled, true);
    assert.equal(document.querySelector<HTMLButtonElement>('[aria-label="Back to Today"]')?.disabled, true);
    await act(async () => { rejectWrite(new Error("Network failed")); });
    assert.equal(completions, 0);
    assert.equal(save.disabled, false);
    assert.match(document.body.textContent ?? "", /Network failed/);
  } finally {
    await act(async () => { root.unmount(); });
  }
});
