import test from "node:test";
import assert from "node:assert/strict";

import "./test-dom";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";

import { formatGenerationElapsedLabel } from "../lib/generation-elapsed";
import { publishGenerationTerminalJob } from "../lib/generation-terminal-event";
import type { GenerationJobResponse } from "../lib/types";
import {
  GenerationStatusProvider,
  shouldPollGenerationStatus,
  useGenerationStatus,
  type GenerationStatusContextValue,
} from "./generation-status-provider";
import { getGenerationStatusTarget } from "./global-generation-status";

// The split-brain race this file exists for:
//
//   1. The global provider holds "running" for job J.
//   2. The /generate controller sees J reach review_required.
//   3. The controller clears the shared pending-generation record.
//   4. The provider must still learn J is terminal — a same-tab localStorage
//      write fires no `storage` event, and the poll used to be gated on that
//      very record, so the provider could never find out on its own.
//   5. The ribbon must switch to the admin-review message.
//   6. The elapsed clock must stop, permanently.
//
// The assertions below run against the real provider with a stubbed backend.
// The ribbon's own rendering needs the auth + routing providers, so the
// user-visible strings are asserted on the two values the ribbon renders
// verbatim: `statusMessage`, and `formatGenerationElapsedLabel` over
// `startedAtMs`/`endedAtMs` (the identical call the ribbon makes).

const TOKEN = "test-token";
const PENDING_PREFIX = "unlxck:pending-generation:";

// The provider drops a live job it has not heard from in 10 minutes, so the
// fixture is anchored to the current clock: a build that started 4m 52s ago
// and had its triage hold land at 4m 39s.
const ELAPSED_MS = 292_000;
const REVIEW_OFFSET_MS = 279_000;

type RaceFixture = {
  startedAtMs: number;
  reviewAtMs: number;
  runningJob: GenerationJobResponse;
  reviewRequiredJob: GenerationJobResponse;
  // The backend reported `failed`, but a plan was written anyway — the
  // controller opens it and reports `completed`.
  failedWithSavedPlanJob: GenerationJobResponse;
};

function buildRaceFixture(nowMs = Date.now()): RaceFixture {
  const startedAtMs = nowMs - ELAPSED_MS;
  const reviewAtMs = startedAtMs + REVIEW_OFFSET_MS;
  const iso = (ms: number) => new Date(ms).toISOString();

  const runningJob: GenerationJobResponse = {
    job_id: "job-race-1",
    athlete_id: "athlete-1",
    client_request_id: "req-race-1",
    status: "running",
    created_at: iso(startedAtMs),
    updated_at: iso(nowMs - 5_000),
    started_at: iso(startedAtMs),
    heartbeat_at: iso(nowMs - 5_000),
    progress_milestones: [
      {
        code: "stage2_model_call",
        label: "Stage 2 model call",
        detail: "Building the plan.",
        at: iso(startedAtMs + 66_000),
      },
    ],
  };

  return {
    startedAtMs,
    reviewAtMs,
    runningJob,
    reviewRequiredJob: {
      ...runningJob,
      status: "review_required",
      updated_at: iso(reviewAtMs),
      completed_at: iso(reviewAtMs),
      plan_id: null,
      latest_plan_id: null,
      requires_admin_resume: true,
      stage2_status: "triage_blocked",
    },
    failedWithSavedPlanJob: {
      ...runningJob,
      status: "failed",
      updated_at: iso(reviewAtMs),
      completed_at: iso(reviewAtMs),
      plan_id: "plan-recovered-1",
      latest_plan_id: null,
      error: "Stage 2 worker exited before reporting success.",
      can_retry: true,
    },
  };
}

type BackendState = {
  active: GenerationJobResponse | null;
  job: GenerationJobResponse;
  latest: GenerationJobResponse | null;
};

function installFetchStub(state: BackendState): () => void {
  const originalFetch = globalThis.fetch;

  globalThis.fetch = (async (input: RequestInfo | URL) => {
    const url = String(typeof input === "string" || input instanceof URL ? input : input.url);
    const json = (body: unknown) =>
      new Response(JSON.stringify(body), {
        status: 200,
        headers: { "content-type": "application/json" },
      });

    if (url.includes("/api/generation-jobs/active")) {
      return json(state.active);
    }
    if (url.includes("/api/generation-jobs/latest")) {
      return json(state.latest);
    }
    if (url.includes("/api/generation-jobs/")) {
      return json(state.job);
    }
    throw new Error(`unexpected request: ${url}`);
  }) as typeof fetch;

  return () => {
    globalThis.fetch = originalFetch;
  };
}

function clearPendingRecords(): void {
  Object.keys(window.localStorage)
    .filter((key) => key.startsWith(PENDING_PREFIX))
    .forEach((key) => window.localStorage.removeItem(key));
}

function listPendingRecords(): string[] {
  return Object.keys(window.localStorage).filter((key) => key.startsWith(PENDING_PREFIX));
}

async function settle() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();
  });
}

type Harness = {
  read: () => GenerationStatusContextValue;
  refresh: () => Promise<void>;
  unmount: () => Promise<void>;
};

async function mountProvider(): Promise<Harness> {
  let latestValue: GenerationStatusContextValue | null = null;

  function Probe() {
    latestValue = useGenerationStatus();
    return null;
  }

  const container = document.createElement("div");
  document.body.appendChild(container);
  const root: Root = createRoot(container);

  await act(async () => {
    root.render(
      <GenerationStatusProvider token={TOKEN}>
        <Probe />
      </GenerationStatusProvider>,
    );
  });
  // Let the provider's one-shot mount check fire and finish before the test
  // starts driving it, so a stray timer cannot land in the middle of the race
  // being reproduced. Only the 15s poll interval remains after this.
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 1_200));
  });
  await settle();

  const read = () => {
    if (!latestValue) {
      throw new Error("provider never rendered");
    }
    return latestValue;
  };

  return {
    read,
    refresh: async () => {
      await act(async () => {
        read().refreshStatus();
      });
      await settle();
    },
    unmount: async () => {
      await act(async () => {
        root.unmount();
      });
      container.remove();
    },
  };
}

function elapsedLabelFor(value: GenerationStatusContextValue, nowMs: number): string | null {
  return formatGenerationElapsedLabel({
    startedAtMs: value.startedAtMs,
    endedAtMs: value.endedAtMs,
    nowMs,
  });
}

test("the ribbon stops when the generate controller resolves a job behind its back", async () => {
  clearPendingRecords();
  const { startedAtMs, reviewAtMs, runningJob, reviewRequiredJob } = buildRaceFixture();
  const state: BackendState = { active: runningJob, job: runningJob, latest: null };
  const restoreFetch = installFetchStub(state);
  const harness = await mountProvider();

  try {
    // 1. Provider holds running.
    await harness.refresh();
    assert.equal(harness.read().phase, "running");
    assert.equal(harness.read().statusMessage, "Generating plan...");
    assert.equal(harness.read().startedAtMs, startedAtMs);
    assert.equal(harness.read().endedAtMs, null);
    // A live job's clock moves.
    assert.equal(elapsedLabelFor(harness.read(), startedAtMs + 226_000), "3m 46s");
    assert.equal(elapsedLabelFor(harness.read(), startedAtMs + 292_000), "4m 52s");

    // 2 + 3. The generate controller sees review_required and clears the
    // shared pending record. The backend agrees the job is over, but nothing
    // has told this provider — and no `storage` event fires for a same-tab
    // write.
    state.active = null;
    state.job = reviewRequiredJob;
    state.latest = reviewRequiredJob;
    clearPendingRecords();
    await settle();
    assert.equal(harness.read().phase, "running", "no notification yet: the ribbon is still stale");

    // 4. The controller publishes the terminal job in-tab.
    await act(async () => {
      publishGenerationTerminalJob(reviewRequiredJob);
    });
    await settle();

    // 5. The ribbon switches to the admin-review message.
    const settled = harness.read();
    assert.equal(settled.phase, "completed");
    assert.equal(settled.terminalStatus, "review_required");
    assert.equal(settled.requiresAdminResume, true);
    assert.equal(settled.statusMessage, "Admin review required.");
    assert.equal(settled.jobId, reviewRequiredJob.job_id);

    // 6. The elapsed time stops, permanently: it is now a subtraction of two
    // fixed backend timestamps, so no later render can advance it.
    assert.equal(settled.endedAtMs, reviewAtMs);
    assert.equal(elapsedLabelFor(settled, startedAtMs + 292_000), "4m 39s");
    assert.equal(elapsedLabelFor(settled, startedAtMs + 3_600_000), "4m 39s");

    // The terminal handoff must not leave a pending record behind that could
    // resurrect the job as "in flight".
    assert.deepEqual(listPendingRecords(), []);
  } finally {
    await harness.unmount();
    restoreFetch();
    clearPendingRecords();
  }
});

test("a job that resolves with no in-tab event is still reconciled from the retained job id", async () => {
  // The event is the fast path, not the only path. Even with the pending
  // record gone and the backend reporting no active job, the provider keeps
  // checking the exact job it was following until the backend confirms a
  // terminal status — the conditional-polling trap this closes is what let a
  // "running" ribbon outlive its job indefinitely.
  clearPendingRecords();
  const { startedAtMs, reviewAtMs, runningJob, reviewRequiredJob } = buildRaceFixture();
  const state: BackendState = { active: runningJob, job: runningJob, latest: null };
  const restoreFetch = installFetchStub(state);
  const harness = await mountProvider();

  try {
    await harness.refresh();
    assert.equal(harness.read().phase, "running");

    state.active = null;
    state.job = reviewRequiredJob;
    state.latest = reviewRequiredJob;
    clearPendingRecords();

    await harness.refresh();

    const settled = harness.read();
    assert.equal(settled.jobId, reviewRequiredJob.job_id);
    assert.equal(settled.phase, "completed");
    assert.equal(settled.terminalStatus, "review_required");
    assert.equal(settled.statusMessage, "Admin review required.");
    assert.equal(settled.endedAtMs, reviewAtMs);
    assert.equal(elapsedLabelFor(settled, startedAtMs + 3_600_000), "4m 39s");
  } finally {
    await harness.unmount();
    restoreFetch();
    clearPendingRecords();
  }
});

test("a failed job that saved a plan reaches the ribbon as a ready plan, not a failure", async () => {
  // The controller resolves this outcome as `completed` and navigates to the
  // plan, but the job it publishes still says `failed`. Reading that status
  // literally put a build-failure ribbon on top of the athlete's finished
  // plan, and dropped the plan id the ribbon needed to link to it.
  clearPendingRecords();
  const { startedAtMs, reviewAtMs, runningJob, failedWithSavedPlanJob } = buildRaceFixture();
  const state: BackendState = { active: runningJob, job: runningJob, latest: null };
  const restoreFetch = installFetchStub(state);
  const harness = await mountProvider();

  try {
    await harness.refresh();
    assert.equal(harness.read().phase, "running");

    // The controller finishes: plan saved, pending record cleared, terminal
    // job published in-tab.
    state.active = null;
    state.job = failedWithSavedPlanJob;
    state.latest = failedWithSavedPlanJob;
    clearPendingRecords();

    await act(async () => {
      publishGenerationTerminalJob(failedWithSavedPlanJob);
    });
    await settle();

    const settled = harness.read();
    assert.notEqual(settled.phase, "failed");
    assert.equal(settled.phase, "completed");
    assert.equal(settled.terminalStatus, "completed");
    assert.equal(settled.isStalled, false);
    // The plan id survives, so the ribbon can open the recovered plan.
    assert.equal(settled.planId, "plan-recovered-1");
    assert.equal(settled.statusMessage, "Your plan is saved and ready.");
    assert.notEqual(settled.statusMessage, "Your plan build stopped.");
    // The ribbon links to the plan instead of rendering its failure branch,
    // which offers only "Retry" / "Stop build".
    assert.equal(
      getGenerationStatusTarget(
        settled.phase,
        settled.planId,
        settled.terminalStatus,
        settled.source,
        settled.athleteId,
      ),
      "/plans/plan-recovered-1",
    );
    // And the clock still froze on the backend's terminal timestamp.
    assert.equal(settled.endedAtMs, reviewAtMs);
    assert.equal(elapsedLabelFor(settled, startedAtMs + 3_600_000), "4m 39s");
  } finally {
    await harness.unmount();
    restoreFetch();
    clearPendingRecords();
  }
});

test("the poll reaches the same verdict on a failed job that saved a plan", async () => {
  // The event is the fast path; a provider that only ever polls must not
  // disagree with it about what this job means.
  clearPendingRecords();
  const { runningJob, failedWithSavedPlanJob } = buildRaceFixture();
  const state: BackendState = { active: runningJob, job: runningJob, latest: null };
  const restoreFetch = installFetchStub(state);
  const harness = await mountProvider();

  try {
    await harness.refresh();
    assert.equal(harness.read().phase, "running");

    state.active = null;
    state.job = failedWithSavedPlanJob;
    state.latest = failedWithSavedPlanJob;
    clearPendingRecords();

    await harness.refresh();

    const settled = harness.read();
    assert.equal(settled.phase, "completed");
    assert.equal(settled.terminalStatus, "completed");
    assert.equal(settled.planId, "plan-recovered-1");
    assert.equal(settled.statusMessage, "Your plan is saved and ready.");
  } finally {
    await harness.unmount();
    restoreFetch();
    clearPendingRecords();
  }
});

test("the poll survives the pending record being cleared out from under it", () => {
  // The gate that caused the bug, in isolation.
  assert.equal(shouldPollGenerationStatus(null, false), false);
  assert.equal(shouldPollGenerationStatus(null, true), true);
  assert.equal(shouldPollGenerationStatus("job-race-1", false), true);
  assert.equal(shouldPollGenerationStatus("job-race-1", true), true);
});
