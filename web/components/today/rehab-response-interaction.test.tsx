import test from "node:test";
import assert from "node:assert/strict";

import "../test-dom";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";

import { RehabResponsePrompt } from "./rehab-response-prompt";
import type { RehabResponsePrompt as RehabResponsePromptModel } from "@/lib/types";

process.env.NEXT_PUBLIC_API_DEBUG = "false";

function mount(): { container: HTMLElement; root: Root } {
  const container = document.createElement("div");
  document.body.appendChild(container);
  return { container, root: createRoot(container) };
}

function cleanup(container: HTMLElement, root: Root) {
  act(() => root.unmount());
  container.remove();
}

async function settle() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

function buttonByText(container: HTMLElement, text: string): HTMLButtonElement {
  const match = Array.from(container.querySelectorAll("button")).find(
    (button) => button.textContent?.trim() === text,
  );
  assert.ok(match, `expected a "${text}" button`);
  return match as HTMLButtonElement;
}

function chipInGroup(container: HTMLElement, groupId: string, label: string): HTMLButtonElement {
  const group = container.querySelector(`[aria-labelledby="${groupId}"]`);
  assert.ok(group, `expected the ${groupId} question`);
  const match = Array.from(group.querySelectorAll("button")).find(
    (button) => button.textContent?.trim() === label,
  );
  assert.ok(match, `expected a "${label}" chip in ${groupId}`);
  return match as HTMLButtonElement;
}

function ankle(): RehabResponsePromptModel {
  return {
    injury_id: "injury-ankle",
    injury_episode_id: "11111111-1111-1111-1111-111111111111",
    injury_label: "LEFT ANKLE",
    body_region: "ankle",
    side: "left",
    drill_ids: ["ankle_sprain_single_leg_balance_on_foam_pad"],
    during_question: "How did it feel during the rehab work?",
    during_options: ["better", "same", "worse", "not_sure"],
    limit_question: "Did you have to reduce or stop because of it?",
    limit_options: ["no", "reduced", "stopped"],
  };
}

function knee(): RehabResponsePromptModel {
  return {
    ...ankle(),
    injury_id: "injury-knee",
    injury_episode_id: "22222222-2222-2222-2222-222222222222",
    injury_label: "RIGHT KNEE",
    body_region: "knee",
    side: "right",
    drill_ids: ["knee_pain_terminal_knee_extensions_tkes"],
  };
}

function render(
  root: Root,
  prompts: RehabResponsePromptModel[],
  onDismiss: () => void = () => {},
) {
  act(() => {
    root.render(
      <RehabResponsePrompt
        token="test-token"
        planId="plan-1"
        sessionId="session-1"
        prompts={prompts}
        onDismiss={onDismiss}
      />,
    );
  });
}

function captureFetch(status = 201, body: unknown = { recorded_exposure_ids: ["e1"], recorded_injury_ids: ["injury-ankle"] }) {
  const calls: Array<{ url: string; payload: Record<string, unknown> }> = [];
  const original = globalThis.fetch;
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    calls.push({
      url: String(input),
      payload: JSON.parse(String(init?.body ?? "{}")),
    });
    return new Response(JSON.stringify(body), {
      status,
      headers: { "content-type": "application/json" },
    });
  }) as typeof fetch;
  return { calls, restore: () => void (globalThis.fetch = original) };
}

test("no prompts means no block at all — a normal session shows nothing", () => {
  const { container, root } = mount();
  render(root, []);

  assert.equal(container.textContent?.trim(), "");

  cleanup(container, root);
});

test("each injury is asked about by name, with the server's own questions", () => {
  const { container, root } = mount();
  render(root, [ankle(), knee()]);

  const text = container.textContent ?? "";
  assert.match(text, /LEFT ANKLE/);
  assert.match(text, /RIGHT KNEE/);
  assert.match(text, /How did it feel during the rehab work\?/);
  assert.match(text, /Did you have to reduce or stop because of it\?/);
  // The athlete is asked what they observed, never what it means.
  assert.doesNotMatch(text, /diagnos|mechanism|tear|sprain grade/i);
  // No free text and no pain slider: a categorical answer is not a 0-10 score.
  assert.equal(container.querySelectorAll("textarea").length, 0);
  assert.equal(container.querySelectorAll("input").length, 0);

  cleanup(container, root);
});

test("save stays disabled until an injury is fully answered", async () => {
  const { container, root } = mount();
  render(root, [ankle()]);

  assert.equal(buttonByText(container, "Save").disabled, true);

  act(() => {
    chipInGroup(container, "rehab-during-injury-ankle", "Worse").click();
  });
  await settle();
  // Half an answer is an unfinished question, not a partial observation.
  assert.equal(buttonByText(container, "Save").disabled, true);

  act(() => {
    chipInGroup(container, "rehab-limit-injury-ankle", "Reduced it").click();
  });
  await settle();
  assert.equal(buttonByText(container, "Save").disabled, false);

  cleanup(container, root);
});

test("answering returns the server-issued episode context with the athlete's words", async () => {
  const { calls, restore } = captureFetch();
  const { container, root } = mount();
  render(root, [ankle()]);

  act(() => {
    chipInGroup(container, "rehab-during-injury-ankle", "Worse").click();
  });
  act(() => {
    chipInGroup(container, "rehab-limit-injury-ankle", "Stopped").click();
  });
  await settle();
  act(() => {
    buttonByText(container, "Save").click();
  });
  await settle();

  assert.equal(calls.length, 1);
  assert.match(calls[0].url, /\/api\/today\/rehab-responses$/);
  assert.deepEqual(calls[0].payload.answers, [
    {
      injury_id: "injury-ankle",
      injury_episode_id: "11111111-1111-1111-1111-111111111111",
      during_response: "worse",
      limit_response: "stopped",
    },
  ]);
  // Drill, side and demand remain the server's to resolve.
  assert.deepEqual(Object.keys(calls[0].payload).sort(), [
    "answers",
    "plan_id",
    "session_id",
    "training_day",
  ]);
  assert.match(container.textContent ?? "", /Logged against your injury/);

  restore();
  cleanup(container, root);
});

test("an unanswered injury is left out rather than defaulted", async () => {
  const { calls, restore } = captureFetch();
  const { container, root } = mount();
  render(root, [ankle(), knee()]);

  act(() => {
    chipInGroup(container, "rehab-during-injury-ankle", "Better").click();
  });
  act(() => {
    chipInGroup(container, "rehab-limit-injury-ankle", "No").click();
  });
  await settle();
  act(() => {
    buttonByText(container, "Save").click();
  });
  await settle();

  // The knee was never answered, so nothing is reported for the knee. A default
  // "same" would be an observation the athlete never made.
  assert.deepEqual(calls[0].payload.answers, [
    {
      injury_id: "injury-ankle",
      injury_episode_id: "11111111-1111-1111-1111-111111111111",
      during_response: "better",
      limit_response: "no",
    },
  ]);

  restore();
  cleanup(container, root);
});

test("tapping a selected chip clears it, so a mis-tap is not locked in", async () => {
  const { container, root } = mount();
  render(root, [ankle()]);

  act(() => {
    chipInGroup(container, "rehab-during-injury-ankle", "Worse").click();
  });
  act(() => {
    chipInGroup(container, "rehab-limit-injury-ankle", "No").click();
  });
  await settle();
  assert.equal(buttonByText(container, "Save").disabled, false);

  act(() => {
    chipInGroup(container, "rehab-during-injury-ankle", "Worse").click();
  });
  await settle();
  assert.equal(chipInGroup(container, "rehab-during-injury-ankle", "Worse").getAttribute("aria-pressed"), "false");
  assert.equal(buttonByText(container, "Save").disabled, true);

  cleanup(container, root);
});

test("skip sends nothing", async () => {
  const { calls, restore } = captureFetch();
  const { container, root } = mount();
  let dismissed = false;
  render(root, [ankle()], () => {
    dismissed = true;
  });

  act(() => {
    chipInGroup(container, "rehab-during-injury-ankle", "Worse").click();
  });
  await settle();
  act(() => {
    buttonByText(container, "Skip").click();
  });
  await settle();

  assert.equal(dismissed, true);
  assert.equal(calls.length, 0);

  restore();
  cleanup(container, root);
});

test("a failed save surfaces the error and keeps the answers editable", async () => {
  const { restore } = captureFetch(500, { detail: "storage unavailable" });
  const { container, root } = mount();
  render(root, [ankle()]);

  act(() => {
    chipInGroup(container, "rehab-during-injury-ankle", "Same").click();
  });
  act(() => {
    chipInGroup(container, "rehab-limit-injury-ankle", "No").click();
  });
  await settle();
  act(() => {
    buttonByText(container, "Save").click();
  });
  await settle();

  assert.ok(container.querySelector('[role="alert"]'), "expected the failure to be reported");
  assert.doesNotMatch(container.textContent ?? "", /Logged against your injury/);
  assert.equal(buttonByText(container, "Save").disabled, false);

  restore();
  cleanup(container, root);
});
