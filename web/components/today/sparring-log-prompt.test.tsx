import test from "node:test";
import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";

import { AppSessionContext } from "@/components/auth-provider";
import { sparringSummary } from "@/components/session-timer/session-timer";
import { ToastProvider } from "@/components/toast-provider";
import { createTimerState } from "@/lib/session-timer/engine";
import type { TimerItem } from "@/lib/session-timer/plan";

import { defaultIntensity, SparringLogPrompt, type SparringDraft } from "./sparring-log-prompt";

const DRAFT: SparringDraft = {
  source: "contact",
  planId: "plan-1",
  sessionId: null,
  plannedIntensity: "hard",
  title: "Hard sparring",
  rounds: 5,
  roundSeconds: 180,
};

function render(consent: boolean): string {
  const me = { profile: { health_consent_granted: consent } };
  return renderToStaticMarkup(
    <AppSessionContext.Provider value={{ session: null, me } as never}>
      <ToastProvider>
        <SparringLogPrompt token="t" draft={DRAFT} onDismiss={() => undefined} />
      </ToastProvider>
    </AppSessionContext.Provider>,
  );
}

test("the log opens pre-filled from the plan and the timer", () => {
  const html = render(true);
  assert.match(html, /Log your sparring/);
  assert.match(html, /Hard sparring · takes 15 seconds/);
  // Planned hard sparring starts on Hard; the athlete corrects it if needed.
  assert.match(html, /aria-pressed="true"[^>]*>Hard</);
  // Rounds come from the timer.
  assert.match(html, /aria-live="polite">5</);
  assert.match(html, /Got rocked or dropped\?/);
  // "No" is the default, so no safety message until "Yes" is picked.
  assert.doesNotMatch(html, /No more contact today/);
});

test("without health-data consent the sparring log is never shown", () => {
  const html = render(false);
  assert.doesNotMatch(html, /Log your sparring|rocked/);
  assert.doesNotMatch(html, /<section/);
});

test("planned intensity maps to the starting answer", () => {
  assert.equal(defaultIntensity("hard"), "hard");
  assert.equal(defaultIntensity("light"), "light");
  assert.equal(defaultIntensity("technical"), "light");
  assert.equal(defaultIntensity("contact"), "medium");
  assert.equal(defaultIntensity(null), undefined);
});

test("the sparring summary counts only completed sparring rounds", () => {
  const items: TimerItem[] = [
    {
      kind: "interval",
      id: "spar",
      title: "Hard sparring",
      detail: null,
      blockType: "sparring",
      rounds: 6,
      workSec: 180,
      restSec: 60,
      sparring: true,
      needsSetup: false,
    },
    {
      kind: "interval",
      id: "bag",
      title: "Bag",
      detail: null,
      blockType: "conditioning",
      rounds: 3,
      workSec: 120,
      restSec: 60,
      sparring: false,
      needsSetup: false,
    },
  ];
  const state = { ...createTimerState(items), completed: [4, 3] };
  assert.deepEqual(sparringSummary(state), { rounds: 4, roundSeconds: 180, plannedIntensity: null });
  const planned = { ...state, items: [{ ...items[0], plannedIntensity: "hard" as const }, items[1]] };
  assert.equal(sparringSummary(planned)?.plannedIntensity, "hard");
  assert.equal(sparringSummary(createTimerState([items[1]])), null);
});
